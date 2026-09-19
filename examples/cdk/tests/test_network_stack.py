from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_app.config import ValidationConfig
from cdk_app.stack import LiveValidationStack


def synthesize_network():
    config = ValidationConfig(
        password="synthesis-only-value-A1",
        expires_at="2026-08-31",
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


def test_network_is_public_without_nat_or_operator_eip():
    template = synthesize_network()
    template.resource_count_is("AWS::EC2::VPC", 1)
    template.resource_count_is("AWS::EC2::Subnet", 3)
    template.resource_count_is("AWS::EC2::InternetGateway", 1)
    template.resource_count_is("AWS::EC2::NatGateway", 0)
    template.resource_count_is("AWS::EC2::EIP", 0)
    template.resource_count_is("AWS::EC2::SubnetRouteTableAssociation", 3)
    template.has_resource_properties(
        "AWS::EC2::Route",
        {"DestinationCidrBlock": "0.0.0.0/0"},
    )


def test_security_group_allows_only_operator_host_on_redshift_port():
    template = synthesize_network()
    template.resource_count_is("AWS::EC2::SecurityGroup", 1)
    template.resource_count_is("AWS::EC2::SecurityGroupIngress", 1)
    template.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {
            "CidrIp": "8.8.8.8/32",
            "FromPort": 5439,
            "ToPort": 5439,
            "IpProtocol": "tcp",
        },
    )
    ingress = template.find_resources("AWS::EC2::SecurityGroupIngress")
    assert all(
        resource["Properties"]["CidrIp"] != "0.0.0.0/0"
        for resource in ingress.values()
    )
