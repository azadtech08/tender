environment          = "staging"
aws_region           = "ap-south-1"

# Networking
vpc_cidr         = "10.0.0.0/16"
public_subnets   = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

# Database (use a stronger password in prod)
db_instance_class    = "db.t4g.small"
db_allocated_storage = 20
db_name              = "gem_tender"
db_username          = "gem"
# db_password        = set via TF_VAR_db_password or -var flag — never commit

# Redis
redis_node_type = "cache.t4g.micro"

# ECS sizing (lean for staging)
api_cpu              = 256
api_memory           = 512
worker_cpu           = 512
worker_memory        = 1024
api_desired_count    = 1
worker_desired_count = 1

# TLS (fill in after ACM cert is issued)
# acm_certificate_arn = "arn:aws:acm:ap-south-1:123456789012:certificate/..."
# api_domain          = "api.staging.gemtender.com"
