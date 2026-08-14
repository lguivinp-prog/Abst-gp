variable "environment" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_oidc_thumbprint" {
  type    = string
  default = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"
}
