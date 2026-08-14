data "aws_iam_policy_document" "eso_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets-sa"]
    }
  }
}

resource "aws_iam_role" "eso_role" {
  name               = "abast-gp-${var.environment}-eso-role"
  assume_role_policy = data.aws_iam_policy_document.eso_assume_role_policy.json
}

resource "aws_iam_role_policy" "eso_policy" {
  name = "abast-gp-${var.environment}-eso-policy"
  role = aws_iam_role.eso_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:ListSecretVersionIds"
        ]
        Resource = ["*"]
      }
    ]
  })
}

data "aws_iam_policy_document" "s3_assume_role_policy" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:abst-gp-${var.environment}:backend-api-sa", "system:serviceaccount:abst-gp-${var.environment}:ocr-worker-sa"]
    }
  }
}

resource "aws_iam_role" "s3_access_role" {
  name               = "abast-gp-${var.environment}-s3-access-role"
  assume_role_policy = data.aws_iam_policy_document.s3_assume_role_policy.json
}

resource "aws_iam_role_policy" "s3_access_policy" {
  name = "abast-gp-${var.environment}-s3-access-policy"
  role = aws_iam_role.s3_access_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}
