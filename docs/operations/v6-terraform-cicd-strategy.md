# Terraform CI/CD Strategy and Cost Review

This document formalizes the Continuous Integration / Continuous Deployment (CI/CD) strategy for Abast-GP V6 Infrastructure as Code, ensuring absolute security, traceability, and financial governance before any cloud resources are created.

## 1. Authentication Strategy: OpenID Connect (OIDC)
Permanent AWS Access Keys (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are **strictly prohibited** in GitHub Secrets or CI/CD platforms. 

We utilize **OIDC Federation** to establish a trust relationship between GitHub Actions and AWS IAM.
- **Workflow**: 
  1. The pipeline requests a short-lived JSON Web Token (JWT) from GitHub's OIDC provider.
  2. The `aws-actions/configure-aws-credentials` step exchanges this JWT via AWS STS (`AssumeRoleWithWebIdentity`).
  3. AWS grants temporary credentials valid only for the duration of the job (max 1 hour).

## 2. IAM Least Privilege Model
The assumed role (`AbastGP-GithubActions-TerraformRole`) must have restricted policies:
- **Trust Policy**: Restricted to `repo:Organization/Abast-gp:ref:refs/heads/main` and specific branch patterns to prevent lateral movement.
- **Permissions Policy**:
  - `s3:*` scoped *only* to the Terraform State Bucket.
  - `dynamodb:*` scoped *only* to the Terraform State Lock Table.
  - Granular permissions for actual resources (EKS, EC2, RDS, VPC) bounded by `Condition` keys mandating `abast-gp` tags.

## 3. Terraform Workflow Execution
- **`terraform fmt`**: Enforces canonical formatting across all modules.
- **`terraform init`**: Bootstraps the remote S3 backend securely.
- **`terraform validate`**: Catches static syntax errors.
- **`terraform plan`**: Executed automatically on every Pull Request. The output is captured and injected as a comment directly into the PR for architect review.
- **`terraform apply`**: *Currently disabled.* Will require manual approval gates in the CI/CD pipeline post-review.

## 4. Cost Review Preparation Checklist
Before merging any PR containing Terraform changes that trigger an `apply`, the resulting Plan must pass the following financial and architectural checks:

- [ ] **NAT Gateway Strategy**: Confirm NAT Gateways are scoped strictly per-AZ where required, or shared if High Availability is not required for a specific non-prod tier. (NAT Gateways charge hourly + per GB processed).
- [ ] **RDS Sizing**: Verify the `instance_class` is appropriate (e.g., `db.t4g.micro` for Dev, `db.r6g.large` for Prod) and Multi-AZ is only enabled where strictly necessary.
- [ ] **EKS Nodes**: Ensure `min_size` and `desired_size` on Managed Node Groups don't result in heavily over-provisioned idle compute. Spot Instances must be prioritized for OCR Workers.
- [ ] **Logging Retention**: CloudWatch / S3 logging retention must have lifecycle policies. Indefinite retention is not permitted unless legally required.
