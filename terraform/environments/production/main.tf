provider "aws" {
  region = var.region
}

module "kms" {
  source      = "../../modules/kms"
  environment = var.environment
}

module "networking" {
  source                = "../../modules/networking"
  environment           = var.environment
  vpc_cidr              = var.vpc_cidr
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  database_subnet_cidrs = var.database_subnet_cidrs
  azs                   = var.azs
}

module "eks" {
  source             = "../../modules/eks"
  environment        = var.environment
  private_subnet_ids = module.networking.private_subnets
}

module "rds" {
  source                = "../../modules/rds"
  environment           = var.environment
  database_subnet_ids   = module.networking.database_subnets
  vpc_security_group_id = module.networking.db_security_group_id
  db_instance_class     = var.db_instance_class
  db_username           = var.db_username
  db_password           = var.db_password
  kms_key_arn           = module.kms.kms_key_arn
}

module "s3" {
  source      = "../../modules/s3"
  environment = var.environment
  kms_key_arn = module.kms.kms_key_arn
}

module "iam" {
  source            = "../../modules/iam"
  environment       = var.environment
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  s3_bucket_arn     = module.s3.bucket_arn
}
