from aws_cdk import CfnOutput, Fn, RemovalPolicy, Stack, Tags, Token
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_redshiftserverless as redshift
from aws_cdk import custom_resources as cr
from constructs import Construct

from cdk_app.config import ValidationConfig


class LiveValidationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: ValidationConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("Purpose", "django-redshift-backend-live-validation")

        vpc = ec2.CfnVPC(
            self,
            "Vpc",
            cidr_block="10.0.0.0/16",
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )
        gateway = ec2.CfnInternetGateway(self, "InternetGateway")
        attachment = ec2.CfnVPCGatewayAttachment(
            self,
            "InternetGatewayAttachment",
            internet_gateway_id=gateway.ref,
            vpc_id=vpc.ref,
        )
        route_table = ec2.CfnRouteTable(self, "PublicRouteTable", vpc_id=vpc.ref)
        route = ec2.CfnRoute(
            self,
            "PublicDefaultRoute",
            route_table_id=route_table.ref,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=gateway.ref,
        )
        route.add_resource_dependency(attachment)

        self.subnet_ids: list[str] = []
        for index, cidr in enumerate(("10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24")):
            subnet = ec2.CfnSubnet(
                self,
                f"PublicSubnet{index + 1}",
                vpc_id=vpc.ref,
                availability_zone=Fn.select(index, Fn.get_azs(config.region)),
                cidr_block=cidr,
                map_public_ip_on_launch=True,
            )
            ec2.CfnSubnetRouteTableAssociation(
                self,
                f"PublicSubnetRouteTableAssociation{index + 1}",
                route_table_id=route_table.ref,
                subnet_id=subnet.ref,
            )
            self.subnet_ids.append(subnet.ref)

        security_group = ec2.CfnSecurityGroup(
            self,
            "RedshiftSecurityGroup",
            group_description="Restrict Redshift validation to the operator host",
            vpc_id=vpc.ref,
        )
        ec2.CfnSecurityGroupIngress(
            self,
            "RedshiftIngress",
            group_id=security_group.attr_group_id,
            cidr_ip=config.allowed_cidr,
            ip_protocol="tcp",
            from_port=5439,
            to_port=5439,
        )
        self.security_group_id = security_group.attr_group_id

        namespace = redshift.CfnNamespace(
            self,
            "Namespace",
            namespace_name=f"{config.prefix}-namespace",
            admin_username="validation_admin",
            admin_user_password=config.password,
            db_name="validation",
        )
        namespace.apply_removal_policy(RemovalPolicy.DESTROY)

        workgroup = redshift.CfnWorkgroup(
            self,
            "Workgroup",
            workgroup_name=f"{config.prefix}-workgroup",
            namespace_name=namespace.ref,
            base_capacity=config.base_capacity,
            max_capacity=config.max_capacity,
            port=5439,
            publicly_accessible=True,
            security_group_ids=[self.security_group_id],
            subnet_ids=self.subnet_ids,
            config_parameters=[
                redshift.CfnWorkgroup.ConfigParameterProperty(
                    parameter_key="require_ssl",
                    parameter_value="true",
                )
            ],
        )
        workgroup.add_resource_dependency(namespace)

        usage_limit = cr.AwsCustomResource(
            self,
            "DailyUsageLimit",
            on_create=cr.AwsSdkCall(
                service="RedshiftServerless",
                action="createUsageLimit",
                parameters={
                    "resourceArn": workgroup.attr_workgroup_workgroup_arn,
                    "usageType": "serverless-compute",
                    "amount": config.daily_rpu_hours,
                    "period": "daily",
                    "breachAction": "deactivate",
                },
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "usageLimit.usageLimitId"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="RedshiftServerless",
                action="deleteUsageLimit",
                parameters={"usageLimitId": cr.PhysicalResourceIdReference()},
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
        )
        usage_limit.node.add_dependency(workgroup)

        for identifier, value in {
            "AcceptedCidr": config.allowed_cidr,
            "AdminUsername": namespace.attr_namespace_admin_username,
            "DatabaseName": namespace.attr_namespace_db_name,
            "EndpointAddress": workgroup.attr_workgroup_endpoint_address,
            "EndpointPort": Token.as_string(workgroup.attr_workgroup_endpoint_port),
            "NamespaceName": namespace.ref,
            "WorkgroupName": workgroup.ref,
        }.items():
            CfnOutput(self, identifier, value=value)
