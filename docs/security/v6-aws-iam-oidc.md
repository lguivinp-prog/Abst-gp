# V6 AWS IAM & OIDC Federation Security Design

This document outlines the strict IAM architecture for executing Terraform via GitHub Actions for the Abast-gp pipeline, relying completely on short-lived tokens via OpenID Connect (OIDC).

## 1. AWS OIDC Provider Configuration
To allow GitHub Actions to authenticate without static access keys, an OIDC provider must be created in AWS:
- **Provider URL**: `https://token.actions.githubusercontent.com`
- **Audience**: `sts.amazonaws.com`
- **Thumbprint**: Managed automatically by AWS (or `6938fd4d98bab03faadb97b34396831e3780aea1`).

## 2. IAM Roles Separation
We implement a **Two-Role Strategy** to minimize blast radius and adhere to Least Privilege.

### A. Terraform Plan Role (`AbastGP-Terraform-Plan-Role`)
- **Usage**: Triggered automatically on Pull Requests.
- **Permissions Policy**:
  - `s3:GetObject`, `s3:ListBucket` (State Bucket)
  - `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem` (Lock Table)
  - `ec2:Describe*`, `rds:Describe*`, `eks:Describe*`, `s3:Describe*` (Read-only access to infrastructure).
  - *No permissions to Create, Update, or Delete AWS resources.*

### B. Terraform Apply Role (`AbastGP-Terraform-Apply-Role`)
- **Usage**: Triggered manually upon PR Merge to `main`, requiring explicit environment approvals.
- **Permissions Policy**:
  - Read/Write to State Bucket and DynamoDB Lock Table.
  - Permissions to Create/Update/Delete resources restricted by condition tags (`abast-gp-dev`, `abast-gp-prod`).
  - *Implicitly requires MFA or GitHub Environment Protection rules.*

## 3. Trust Policy Restrictions
Both roles use a highly restricted Trust Policy to prevent impersonation or lateral movement from other repositories.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YourOrg/Abast-gp:ref:refs/heads/main"
        }
      }
    }
  ]
}
```
*Note: The `sub` condition string ensures that ONLY the `main` branch of the `Abast-gp` repository can assume these roles.*

## 4. Cost Review Matrix
Before applying, the CI/CD pipeline (via Infracost or manual Plan review) must evaluate:
- **RDS Estimate**: Multi-AZ db.t4g.micro for Dev. db.r6g.large for Prod.
- **NAT Gateway Estimate**: Billed hourly per AZ + data processing costs. Dev should use a single NAT; Prod requires Multi-AZ NAT.
- **EKS Estimate**: Fixed $73/month control plane cost + worker nodes EC2 costs.
- **S3 Estimate**: Storage GBs + PUT/GET request costs.
