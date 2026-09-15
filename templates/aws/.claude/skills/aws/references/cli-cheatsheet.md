# AWS CLI cheatsheet

Every command below runs as `aws-vault exec <profile> -- aws ...`. The prefix is omitted for brevity. Never run `aws configure` to store access keys.

## Login and identity

IAM Identity Center profiles ([configure SSO](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html), [sso-session](https://docs.aws.amazon.com/cli/latest/userguide/sso-configure-profile-token.html)):

```ini
# ~/.aws/config  (no ~/.aws/credentials file at all)
[sso-session corp]
sso_start_url  = https://<org>.awsapps.com/start
sso_region     = eu-west-1
sso_registration_scopes = sso:account:access

[profile dev-ro]
sso_session  = corp
sso_account_id = 111111111111
sso_role_name  = ReadOnly
region = eu-west-1
output = json

[profile prod-deploy]
source_profile = dev-ro
role_arn       = arn:aws:iam::222222222222:role/Deploy
mfa_serial     = arn:aws:iam::111111111111:mfa/me
```

```bash
aws sso login --profile dev-ro                     # opens the browser once per session
aws-vault exec dev-ro -- aws sts get-caller-identity   # confirm account + role before doing anything
aws-vault exec prod-deploy -- terraform plan      # role chaining handled by aws-vault
aws-vault list                                     # sessions and their expiry
aws-vault clear                                    # drop cached sessions
```

`aws-vault exec` also works with `--server` (EC2-metadata-style credential server) for tools that do not read the environment ([aws-vault](https://github.com/99designs/aws-vault)). Config file and env var reference: [config files](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html), [environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html), [assume role profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html).

## Output and filtering

Use `--query` (JMESPath, server-side result shaping) and `--output table|text|json` ([output format](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-output-format.html), [filtering](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-filter.html), [pagination](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html)). Prefer `--filters` (server-side) over `--query` when the API offers it: less data transferred, fewer pages.

```bash
aws ec2 describe-instances --filters Name=tag:Environment,Values=prod \
  --query 'Reservations[].Instances[].{id:InstanceId,type:InstanceType,az:Placement.AvailabilityZone,state:State.Name}' --output table
aws s3api list-buckets --query 'Buckets[].Name' --output text
aws <svc> <op> --no-cli-pager --max-items 50 --starting-token <t>
```

## Inspect (read-only)

```bash
# Account and org
aws organizations describe-organization
aws organizations list-accounts --query 'Accounts[].{id:Id,name:Name,status:Status}' --output table
aws sts get-caller-identity
aws iam list-roles --query 'Roles[?starts_with(RoleName, `AWSReservedSSO`)].RoleName'

# Network
aws ec2 describe-vpcs --query 'Vpcs[].{id:VpcId,cidr:CidrBlock,name:Tags[?Key==`Name`]|[0].Value}' --output table
aws ec2 describe-subnets --filters Name=vpc-id,Values=<vpc> --query 'Subnets[].{id:SubnetId,az:AvailabilityZone,cidr:CidrBlock,public:MapPublicIpOnLaunch}' --output table
aws ec2 describe-security-groups --query 'SecurityGroups[?IpPermissions[?IpRanges[?CidrIp==`0.0.0.0/0`]]].{id:GroupId,name:GroupName}' --output table
aws ec2 describe-transit-gateway-attachments --output table
aws ec2 describe-nat-gateways --query 'NatGateways[].{id:NatGatewayId,state:State,subnet:SubnetId}'

# Compute
aws ec2 describe-instances --query 'Reservations[].Instances[?MetadataOptions.HttpTokens!=`required`].InstanceId'   # IMDSv1 still allowed
aws lambda list-functions --query 'Functions[].{name:FunctionName,rt:Runtime,mem:MemorySize,arch:Architectures[0]}' --output table
aws ecs list-clusters && aws ecs list-services --cluster <c>

# Storage and data
aws s3api get-public-access-block --bucket <b>
aws s3api get-bucket-encryption --bucket <b>
aws s3api get-bucket-versioning --bucket <b>
aws rds describe-db-instances --query 'DBInstances[].{id:DBInstanceIdentifier,multiAZ:MultiAZ,enc:StorageEncrypted,public:PubliclyAccessible}' --output table
aws dynamodb list-tables

# Security posture
aws cloudtrail describe-trails --query 'trailList[].{name:Name,multi:IsMultiRegionTrail,org:IsOrganizationTrail}'
aws guardduty list-detectors
aws securityhub get-findings --filters '{"SeverityLabel":[{"Value":"CRITICAL","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --max-items 20
aws accessanalyzer list-analyzers
aws ec2 get-ebs-encryption-by-default
aws s3control get-public-access-block --account-id <id>

# Cost
aws ce get-cost-and-usage --time-period Start=$(date -d '-30 days' +%F),End=$(date +%F) --granularity MONTHLY --metrics UnblendedCost --group-by Type=TAG,Key=Project
aws budgets describe-budgets --account-id <id>
aws ce get-anomalies --date-interval StartDate=$(date -d '-14 days' +%F)
aws compute-optimizer get-ec2-instance-recommendations --query 'instanceRecommendations[].{id:instanceArn,finding:finding}'
```

Cost APIs: [Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html), [Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html), [Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html).

## Session Manager instead of SSH

No inbound ports, no bastion, no key pairs; every session is logged to CloudTrail and optionally S3/CloudWatch ([Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html), [plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html), [starting sessions](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)). The plugin is already in this shell.

```bash
aws ssm describe-instance-information --query 'InstanceInformationList[].{id:InstanceId,ping:PingStatus,os:PlatformName}' --output table
aws ssm start-session --target i-0123456789abcdef0
aws ssm start-session --target i-0123456789abcdef0 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["5432"],"localPortNumber":["15432"]}'
aws ssm start-session --target i-0123456789abcdef0 --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{"host":["db.internal"],"portNumber":["5432"],"localPortNumber":["15432"]}'
aws ssm send-command --document-name AWS-RunShellScript --targets Key=tag:Role,Values=web --parameters 'commands=["uptime"]'
```

Requires the instance role to include `AmazonSSMManagedInstanceCore` and reachability to SSM endpoints (VPC endpoints in private subnets).

## Parameters and secrets

Read at runtime only; never paste values into chat, logs or files ([Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html), [Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)).

```bash
aws ssm get-parameters-by-path --path /myapp/prod/ --recursive --query 'Parameters[].Name'   # names only
aws secretsmanager list-secrets --query 'SecretList[].{name:Name,rotates:RotationEnabled}'
# Put a local agenix secret into AWS without it touching disk or the terminal:
secret-run --only DB_PASSWORD -- sh -c 'aws secretsmanager put-secret-value --secret-id myapp/prod/db --secret-string "$DB_PASSWORD"'
```

## EKS

```bash
aws eks list-clusters
aws eks describe-cluster --name <c> --query 'cluster.{ver:version,endpointPublic:resourcesVpcConfig.endpointPublicAccess,logging:logging.clusterLogging[0].types}'
aws eks update-kubeconfig --name <c> --alias <c>       # then kubectl uses aws-vault credentials
aws eks list-access-entries --cluster-name <c>
aws eks list-pod-identity-associations --cluster-name <c>
eksctl get cluster && eksctl get nodegroup --cluster <c>
```

Kubeconfig auth uses `aws eks get-token`, so keep running `kubectl` inside `aws-vault exec` ([create kubeconfig](https://docs.aws.amazon.com/eks/latest/userguide/create-kubeconfig.html), [eksctl](https://eksctl.io/)).

## CloudFormation and SAM

```bash
cfn-lint template.yaml                                   # before every deploy
aws cloudformation validate-template --template-body file://template.yaml
aws cloudformation deploy --stack-name <s> --template-file template.yaml --capabilities CAPABILITY_NAMED_IAM --no-execute-changeset
aws cloudformation describe-change-set --change-set-name <arn>     # review, then execute-change-set
aws cloudformation describe-stack-events --stack-name <s> --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`||ResourceStatus==`UPDATE_FAILED`]'
```

[cfn-lint](https://github.com/aws-cloudformation/cfn-lint) catches schema and best-practice errors locally. `sam` is opt-in ([SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)); [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html).

## Safety habits

- Run `aws sts get-caller-identity` before any mutating command; check the account ID against the target.
- Prefer `--dry-run` where supported (`aws ec2 ... --dry-run`) and `--no-execute-changeset` for CloudFormation.
- Set `AWS_REGION` explicitly; do not rely on a default that differs between people.
- Use `--profile` names that encode environment and role (`prod-ro`, `dev-deploy`) so mistakes are visible in the prompt.
- Never pipe `get-secret-value` or `get-parameter --with-decryption` output to the terminal; pass it via `secret-run` or process substitution into the consumer.
