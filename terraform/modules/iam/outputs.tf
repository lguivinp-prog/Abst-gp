output "eso_role_arn" {
  value = aws_iam_role.eso_role.arn
}

output "s3_access_role_arn" {
  value = aws_iam_role.s3_access_role.arn
}
