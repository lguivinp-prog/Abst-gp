# Final Staging Authorization Request

## AWS Account/Environment Target
**Target Environment:** STAGING ONLY (VPC aislada).
**Target Region:** `us-east-1`.

## Exact BOM (48h Lifetime)
1. **Network (IPv4 & Topología):** 
   - 1x VPC, 2x Private Subnets (EC2, RDS, ElastiCache), 2x Public Subnets (ALB, NAT).
   - 1x ALB (Requiere 2x Public IPv4).
   - 1x NAT Gateway (Requiere 1x Public IPv4/EIP).
   - **Cost:** ALB ($1.08) + LCU ($0.40) + NAT ($2.16) + NAT Data ($0.10) + 3x EIP ($0.72) = ~$4.46
2. **Compute:** 2x EC2 `t3.medium` (Linux, 4GB RAM) en Private Subnet = $4.00
3. **Database:** 1x RDS `db.t4g.small` (2 vCPU, 2GB RAM, Single-AZ) en Private Subnet = $1.58
4. **Storage:** 1x 20GB gp3 RDS = $0.15
5. **Proxy:** 1x RDS Proxy (2 vCPU underlying capacity × $0.015 × 48h) = $1.44
6. **Cache:** 1x ElastiCache `cache.t4g.micro` (Redis 7) en Private Subnet = $0.77
7. **CloudWatch:** ACCOUNT_FREE_TIER_VERIFIED (Estimado conservador si excede) = $0.50
**Total Calculated Expected Cost:** ~$12.90 USD
**Total Calculated Upper Bound:** ~$30.00 USD

## Maximum Authorized Spend
**$50 USD**

## Exact Engine Versions & Artifacts
- **Gateway Image:** `abst_api@sha256:8f43a9b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9`
- **Worker Image:** `abst_worker@sha256:9a12b4d8f0c3e7b1a2d5f6c8b9e0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8`
- **Platform:** `linux/amd64`
- **RDS Engine:** `PostgreSQL 16.3-R1`
- **pgvector Extension:** `0.7.0` (Disponible en 16.3).
- **Custom Parameter Group:** Ninguno (Default PG16).

## Data Classification
**SYNTHETIC DATA ONLY**.

## Teardown & TTL (48h Lifetime)
- **T0:** Provisioning.
- **T+48h:** Automático/Manual `terraform destroy`.
- **Cleanup Owner:** SRE Lead.
- **Residual Check:** Post-destroy barrido usando `aws resourcegroupstaggingapi` Y llamadas explícitas service-specific a EC2/EBS/ENI/EIP/RDS/ElastiCache/ALB/NAT para asegurar `RESIDUAL_AUTHORIZED_RESOURCE_COUNT = 0`.

## Failure Injection Authorization
Autorizado para mutar temporalmente (con trap cleanups de revert) los Security Groups aislando DB y Redis.
