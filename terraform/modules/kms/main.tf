resource "aws_kms_key" "main" {
  description             = "KMS key for ${var.environment} environment"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "main" {
  name          = "alias/abast-gp-${var.environment}"
  target_key_id = aws_kms_key.main.key_id
}
