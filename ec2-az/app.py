#!/usr/bin/env python3

# cdk: 1.41.0
from aws_cdk import (
    aws_ec2,
    aws_ecs,
    aws_ecs_patterns,
    aws_servicediscovery,
    aws_iam,
    core,
)

from os import getenv


# Creating a construct that will populate the required objects created in the platform repo such as vpc, ecs cluster, and service discovery namespace
class BasePlatform(core.Construct):
    
    def __init__(self, scope: core.Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.environment_name = 'ecsworkshop'

        # The base platform stack is where the VPC was created, so all we need is the name to do a lookup and import it into this stack for use
        self.vpc = aws_ec2.Vpc.from_lookup(
            self, "VPC",
            vpc_name='{}-base/BaseVPC'.format(self.environment_name)
        )
        
        self.sd_namespace = aws_servicediscovery.PrivateDnsNamespace.from_private_dns_namespace_attributes(
            self, "SDNamespace",
            namespace_name=core.Fn.import_value('NSNAME'),
            namespace_arn=core.Fn.import_value('NSARN'),
            namespace_id=core.Fn.import_value('NSID')
        )
        
        # If using EC2 backed, this will take all security groups assigned to the cluster nodes and create a list
        # This list will be used when importing the cluster
        cluster_output_sec_grp1 = core.Fn.import_value('ECSSecGrpList1')
        cluster_output_sec_grp2 = core.Fn.import_value('ECSSecGrpList2')
        cluster_output_sec_grp3 = core.Fn.import_value('ECSSecGrpList3')
        
        self.ecs_cluster = aws_ecs.Cluster.from_cluster_attributes(
            self, "ECSCluster",
            cluster_name=core.Fn.import_value('ECSClusterName'),
            security_groups=[aws_ec2.SecurityGroup.from_security_group_id(self, "ClusterSecGrp1", cluster_output_sec_grp1), aws_ec2.SecurityGroup.from_security_group_id(self, "ClusterSecGrp2", cluster_output_sec_grp2), aws_ec2.SecurityGroup.from_security_group_id(self, "ClusterSecGrp3", cluster_output_sec_grp3)],
            vpc=self.vpc,
            default_cloud_map_namespace=self.sd_namespace
        )
        

class CapacityProviderEC2Service(core.Stack):
    
    def __init__(self, scope: core.Stack, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        self.base_platform = BasePlatform(self, self.stack_name)

        self.task_image = aws_ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
            image=aws_ecs.ContainerImage.from_registry("adam9098/ecsdemo-capacityproviders:latest"),
            container_port=5000,
            environment={
                'AWS_DEFAULT_REGION': getenv('AWS_DEFAULT_REGION')
            }
        )

        self.load_balanced_service = aws_ecs_patterns.ApplicationLoadBalancedEc2Service(
            self, "EC2CapacityProviderService",
            service_name='ecsdemo-capacityproviders-ec2',
            cluster=self.base_platform.ecs_cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=3,
            #desired_count=12,
            public_load_balancer=True,
            task_image_options=self.task_image,
        )
        
        # This should work, but the default child is not the service cfn, it's a list of cfn service and sec group
        #self.cfn_resource = self.load_balanced_service.service.node.default_child
        self.cfn_resource = self.load_balanced_service.service.node.children[0]
        
        self.cfn_resource.add_deletion_override("Properties.LaunchType")
            
        self.load_balanced_service.task_definition.add_to_task_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    'ecs:ListTasks',
                    'ecs:DescribeTasks'
                ],
                resources=['*']
            )
        )
        

_env = core.Environment(account=getenv('AWS_ACCOUNT_ID'), region=getenv('AWS_DEFAULT_REGION'))
environment = "ecsworkshop"
stack_name = "{}-capacityproviders-ec2".format(environment)
app = core.App()
CapacityProviderEC2Service(app, stack_name, env=_env)
app.synth()
