variable "region" { type = string }
variable "environment" { type = string }
variable "vpc_cidr" { type = string }
variable "public_subnet_cidrs" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "database_subnet_cidrs" { type = list(string) }
variable "azs" { type = list(string) }
variable "db_instance_class" { type = string }
variable "db_username" { type = string }
variable "db_password" { type = string, sensitive = true }
