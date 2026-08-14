resource "aws_db_subnet_group" "main" {
  name       = "abast-gp-${var.environment}-db-subnet-group"
  subnet_ids = var.database_subnet_ids
}

resource "aws_db_parameter_group" "main" {
  name   = "abast-gp-${var.environment}-pg16"
  family = "postgres16"
}

resource "aws_db_instance" "main" {
  identifier                  = "abast-gp-${var.environment}-db"
  engine                      = "postgres"
  engine_version              = "16.1"
  instance_class              = var.db_instance_class
  allocated_storage           = 50
  max_allocated_storage       = 200
  storage_type                = "gp3"
  db_name                     = "abastgp"
  username                    = var.db_username
  password                    = var.db_password
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [var.vpc_security_group_id]
  parameter_group_name        = aws_db_parameter_group.main.name
  multi_az                    = true
  storage_encrypted           = true
  kms_key_id                  = var.kms_key_arn
  backup_retention_period     = 35
  backup_window               = "03:00-04:00"
  copy_tags_to_snapshot       = true
  auto_minor_version_upgrade  = true

  lifecycle {
    prevent_destroy = true
  }
}
