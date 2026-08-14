variable "environment" {
  type = string
}

variable "database_subnet_ids" {
  type = list(string)
}

variable "vpc_security_group_id" {
  type = string
}

variable "db_instance_class" {
  type = string
}

variable "db_username" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "kms_key_arn" {
  type = string
}
