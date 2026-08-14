output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnets" {
  value = aws_subnet.private[*].id
}

output "database_subnets" {
  value = aws_subnet.database[*].id
}

output "db_security_group_id" {
  value = aws_security_group.db.id
}
