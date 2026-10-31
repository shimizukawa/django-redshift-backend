"""Temporary loopback PostgreSQL SSL negotiation probe; no AWS credentials."""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import socket
import ssl
import struct
import tempfile
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import redshift_connector

now = datetime.now(timezone.utc)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(hours=1))
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
    )
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(key, hashes.SHA256())
)

with tempfile.TemporaryDirectory(prefix="redshift-tls-") as directory:
    folder = Path(directory)
    crt, pem = folder / "cert.pem", folder / "key.pem"
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    original_load = ssl.SSLContext.load_verify_locations

    def add_test_trust(context, *args, **kwargs):
        original_load(context, *args, **kwargs)
        original_load(context, cafile=str(crt))

    messages = []

    class Capture(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    logger = logging.getLogger("redshift_connector.core")
    handler = Capture(level=logging.WARNING)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False

    for trusted, host in [
        (True, "localhost"),
        (True, "127.0.0.1"),
        (False, "localhost"),
    ]:
        for mode in (None, "verify-full", "verify-ca"):
            messages.clear()
            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(5)
            port = server.getsockname()[1]
            outcomes = []

            def serve():
                try:
                    with server:
                        raw, _ = server.accept()
                        with raw:
                            raw.settimeout(5)
                            request = raw.recv(8)
                            assert request == struct.pack("!ii", 8, 80877103)
                            raw.sendall(b"S")
                            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                            context.load_cert_chain(str(crt), str(pem))
                            with context.wrap_socket(raw, server_side=True) as secure:
                                if secure.recv(4096):
                                    outcomes.append("startup")
                                    payload = b"SFATAL\x00C28000\x00MTLS_PROBE_COMPLETE\x00\x00"
                                    secure.sendall(
                                        b"E"
                                        + struct.pack("!i", len(payload) + 4)
                                        + payload
                                    )
                except (ssl.SSLError, ConnectionResetError):
                    outcomes.append("tls-rejected")

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            ssl.SSLContext.load_verify_locations = (
                add_test_trust if trusted else original_load
            )
            kwargs = dict(
                user="probe",
                password="dummy",
                database="probe",
                host=host,
                port=port,
                ssl=True,
                timeout=5,
            )
            if mode is not None:
                kwargs["sslmode"] = mode
            try:
                redshift_connector.connect(**kwargs)
                raise AssertionError("Probe endpoint must stop before authentication")
            except redshift_connector.InterfaceError as error:
                reached_startup = "TLS_PROBE_COMPLETE" in str(error)
                if not reached_startup:
                    assert "certificate" in str(error).lower(), type(error).__name__
            finally:
                ssl.SSLContext.load_verify_locations = original_load
            thread.join(6)
            assert not thread.is_alive()
            expected = trusted and (host == "localhost" or mode != "verify-full")
            assert reached_startup == expected
            warned = any("certificate does not name host" in m for m in messages)
            assert warned == (trusted and host == "127.0.0.1" and mode is None)
            assert ("startup" in outcomes) == expected
            assert len(outcomes) == 1, outcomes
            print(
                "trusted" if trusted else "untrusted",
                "match" if host == "localhost" else "mismatch",
                mode or "omitted",
                "TLS-pass" if reached_startup else "TLS-rejected",
                "hostname-warning" if warned else "no-hostname-warning",
                "PASS",
            )
    logger.removeHandler(handler)
