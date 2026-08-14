variable "environment" {
  type = string
}

variable "vpc_security_group_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_secret_arn" {
  type = string
}

variable "db_instance_id" {
  type = string
}
