from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_app.config import ValidationConfig
from cdk_app.stack import LiveValidationStack

PASSWORD = "synthesis-only-value-A1"


def synthesize_template():
    config = ValidationConfig(
        password=PASSWORD,
        account="123456789012",
        region="ap-northeast-1",
        allowed_cidr="8.8.8.8/32",
    )
    stack = LiveValidationStack(
        App(),
        "LiveValidation",
        config=config,
        env=Environment(account=config.account, region=config.region),
    )
    return Template.from_stack(stack)


def test_redshift_namespace_and_workgroup_are_disposable_and_tls_only():
    template = synthesize_template()
    template.has_resource_properties(
        "AWS::RedshiftServerless::Namespace",
        {
            "AdminUsername": "validation_admin",
            "AdminUserPassword": PASSWORD,
            "DbName": "validation",
        },
    )
    template.has_resource_properties(
        "AWS::RedshiftServerless::Workgroup",
        {
            "BaseCapacity": 4,
            "MaxCapacity": 8,
            "Port": 5439,
            "PubliclyAccessible": True,
            "ConfigParameters": [
                {"ParameterKey": "require_ssl", "ParameterValue": "true"}
            ],
        },
    )
    namespace = next(
        iter(template.find_resources("AWS::RedshiftServerless::Namespace").values())
    )
    assert namespace["DeletionPolicy"] == "Delete"
    assert "ManageAdminPassword" not in namespace["Properties"]
    assert "FinalSnapshotName" not in namespace["Properties"]


def test_daily_compute_limit_deactivates_queries():
    template = synthesize_template().to_json()
    custom_resources = {
        key: value
        for key, value in template["Resources"].items()
        if value["Type"] == "Custom::AWS"
    }
    assert len(custom_resources) == 1
    properties = str(next(iter(custom_resources.values()))["Properties"])
    assert "createUsageLimit" in properties
    assert "deleteUsageLimit" in properties
    assert "serverless-compute" in properties
    assert "deactivate" in properties
    assert "daily" in properties
    assert "8" in properties


def test_outputs_are_complete_and_do_not_expose_password():
    template = synthesize_template().to_json()
    outputs = template["Outputs"]
    assert set(outputs) == {
        "AcceptedCidr",
        "AdminUsername",
        "DatabaseName",
        "EndpointAddress",
        "EndpointPort",
        "NamespaceName",
        "WorkgroupName",
    }
    assert PASSWORD not in str(outputs)
    assert all(
        term not in key.lower()
        for key in outputs
        for term in ("password", "secret", "token")
    )
