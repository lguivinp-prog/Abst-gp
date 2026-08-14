output "state_bucket_arn" {
  value = aws_s3_bucket.terraform_state.arn
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.terraform_locks.name
}

output "kms_key_arn" {
  value = aws_kms_key.terraform_state.arn
}
