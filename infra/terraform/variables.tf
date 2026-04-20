variable "environment" {
  description = "Deployment environment (staging | production)"
  type        = string
  default     = "staging"
}

variable "aws_region" {
  description = "AWS region — always ap-south-1 (Mumbai) for India data residency"
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Short project identifier used in resource names"
  type        = string
  default     = "gem"
}

# ── Networking ────────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR for the project VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnets" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnets" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

# ── Container images ──────────────────────────────────────────────────────────
variable "api_image_tag" {
  description = "Docker image tag for the API service"
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Docker image tag for the Celery worker service"
  type        = string
  default     = "latest"
}

# ── RDS ───────────────────────────────────────────────────────────────────────
variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t4g.small"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "gem_tender"
}

variable "db_username" {
  description = "Postgres master username"
  type        = string
  default     = "gem"
  sensitive   = true
}

variable "db_password" {
  description = "Postgres master password — inject from AWS Secrets Manager in CI"
  type        = string
  sensitive   = true
}

# ── ElastiCache ───────────────────────────────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t4g.small"
}

# ── ALB / TLS ─────────────────────────────────────────────────────────────────
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener (ap-south-1)"
  type        = string
  default     = ""
}

variable "api_domain" {
  description = "API domain name, e.g. api.gemtender.com"
  type        = string
  default     = ""
}

# ── ECS task sizing ───────────────────────────────────────────────────────────
variable "api_cpu" {
  description = "CPU units for the API Fargate task (256=0.25 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory (MiB) for the API Fargate task"
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "CPU units for the worker Fargate task"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Memory (MiB) for the worker Fargate task"
  type        = number
  default     = 2048
}

variable "api_desired_count" {
  description = "Desired number of API task replicas"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker task replicas"
  type        = number
  default     = 2
}
