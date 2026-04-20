environment          = "production"
aws_region           = "ap-south-1"

# Networking
vpc_cidr         = "10.1.0.0/16"
public_subnets   = ["10.1.1.0/24", "10.1.2.0/24"]
private_subnets  = ["10.1.101.0/24", "10.1.102.0/24"]

# Database
db_instance_class    = "db.t4g.medium"
db_allocated_storage = 100
db_name              = "gem_tender"
db_username          = "gem"
# db_password        = set via TF_VAR_db_password — NEVER commit this

# Redis
redis_node_type = "cache.t4g.small"

# ECS sizing
api_cpu              = 512
api_memory           = 1024
worker_cpu           = 1024
worker_memory        = 2048
api_desired_count    = 2
worker_desired_count = 2

# TLS (fill in)
# acm_certificate_arn = "arn:aws:acm:ap-south-1:123456789012:certificate/..."
# api_domain          = "api.gemtender.com"
