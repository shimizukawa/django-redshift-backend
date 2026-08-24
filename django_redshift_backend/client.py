from django.db.backends.base.client import BaseDatabaseClient

from .driver import classify_dbshell_options


class DatabaseClient(BaseDatabaseClient):
    executable_name = "psql"

    @classmethod
    def settings_to_cmd_args_env(cls, settings_dict, parameters):
        options = classify_dbshell_options(settings_dict.get("OPTIONS", {}))
        host = settings_dict.get("HOST")
        port = settings_dict.get("PORT")
        dbname = settings_dict.get("NAME")
        user = settings_dict.get("USER")
        password = settings_dict.get("PASSWORD")

        if not dbname and not options.get("service"):
            dbname = "postgres"

        args = [cls.executable_name]
        if user:
            args.extend(["-U", user])
        if host:
            args.extend(["-h", host])
        if port:
            args.extend(["-p", str(port)])
        args.extend(parameters)
        if dbname:
            args.append(dbname)

        option_environment = {
            "passfile": "PGPASSFILE",
            "service": "PGSERVICE",
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
        }
        env = {
            environment: str(options[name])
            for name, environment in option_environment.items()
            if options.get(name)
        }
        if password:
            env["PGPASSWORD"] = str(password)
        return args, env or None
