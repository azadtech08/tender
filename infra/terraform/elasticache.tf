# ── ElastiCache Redis 7 ───────────────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${local.name_prefix}-redis-subnet-group" }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name_prefix}-redis"
  description          = "GeM Tender SaaS — Celery broker + result backend"

  node_type            = var.redis_node_type
  num_cache_clusters   = var.environment == "production" ? 2 : 1
  engine               = "redis"
  engine_version       = "7.1"
  port                 = 6379

  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = var.environment == "production"
  multi_az_enabled           = var.environment == "production"

  snapshot_retention_limit = var.environment == "production" ? 1 : 0
  snapshot_window          = "02:00-03:00"  # 07:30–08:30 IST

  tags = { Name = "${local.name_prefix}-redis" }
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive   = true
}
