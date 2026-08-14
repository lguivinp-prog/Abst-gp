terraform {
  backend "s3" {
    # Configurations will be passed via backend config file during init
    # bucket         = "abast-gp-terraform-state"
    # key            = "ENV/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "abast-gp-terraform-locks"
    # encrypt        = true
  }
}
