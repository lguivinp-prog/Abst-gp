resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "abast-gp-${var.environment}-vpc"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "public" {
  count             = length(var.public_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = element(var.azs, count.index)

  tags = {
    Name = "abast-gp-${var.environment}-public-${count.index}"
    "kubernetes.io/role/elb" = "1"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = element(var.azs, count.index)

  tags = {
    Name = "abast-gp-${var.environment}-private-${count.index}"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

resource "aws_subnet" "database" {
  count             = length(var.database_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.database_subnet_cidrs[count.index]
  availability_zone = element(var.azs, count.index)

  tags = {
    Name = "abast-gp-${var.environment}-db-${count.index}"
  }
}

resource "aws_security_group" "db" {
  name        = "abast-gp-${var.environment}-db-sg"
  description = "Security group for database"
  vpc_id      = aws_vpc.main.id
}
