# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${local.name_prefix}-cluster" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ── CloudWatch log groups ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}/api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name_prefix}/worker"
  retention_in_days = 30
}

# ── Secrets Manager reference (created out-of-band; referenced here) ─────────
# The actual secret value is NOT managed by Terraform (avoids state leak).
# Create with: aws secretsmanager create-secret --name gem-staging/app ...

data "aws_secretsmanager_secret" "app" {
  name = "${local.name_prefix}/app"
}

# ── API Task Definition ───────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
      essential = true

      portMappings = [{
        containerPort = 8000
        hostPort      = 8000
        protocol      = "tcp"
      }]

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "DEBUG",       value = "false" },
      ]

      secrets = [
        { name = "DATABASE_URL",          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:DATABASE_URL::" },
        { name = "SYNC_DATABASE_URL",     valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SYNC_DATABASE_URL::" },
        { name = "REDIS_URL",             valueFrom = "${data.aws_secretsmanager_secret.app.arn}:REDIS_URL::" },
        { name = "JWT_SECRET_KEY",        valueFrom = "${data.aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
        { name = "CLERK_JWKS_URL",        valueFrom = "${data.aws_secretsmanager_secret.app.arn}:CLERK_JWKS_URL::" },
        { name = "CLERK_ISSUER",          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:CLERK_ISSUER::" },
        { name = "STRIPE_SECRET_KEY",     valueFrom = "${data.aws_secretsmanager_secret.app.arn}:STRIPE_SECRET_KEY::" },
        { name = "STRIPE_WEBHOOK_SECRET", valueFrom = "${data.aws_secretsmanager_secret.app.arn}:STRIPE_WEBHOOK_SECRET::" },
        { name = "S3_ENDPOINT",           valueFrom = "${data.aws_secretsmanager_secret.app.arn}:S3_ENDPOINT::" },
        { name = "S3_BUCKET",             valueFrom = "${data.aws_secretsmanager_secret.app.arn}:S3_BUCKET::" },
        { name = "S3_ACCESS_KEY",         valueFrom = "${data.aws_secretsmanager_secret.app.arn}:S3_ACCESS_KEY::" },
        { name = "S3_SECRET_KEY",         valueFrom = "${data.aws_secretsmanager_secret.app.arn}:S3_SECRET_KEY::" },
        { name = "APP_BASE_URL",          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:APP_BASE_URL::" },
        { name = "CORS_ORIGINS",          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:CORS_ORIGINS::" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

# ── Worker Task Definition ────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
      essential = true
      command   = ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=4"]

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
      ]

      secrets = [
        { name = "SYNC_DATABASE_URL", valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SYNC_DATABASE_URL::" },
        { name = "REDIS_URL",         valueFrom = "${data.aws_secretsmanager_secret.app.arn}:REDIS_URL::" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# ── Celery Beat Task Definition ───────────────────────────────────────────────

resource "aws_ecs_task_definition" "beat" {
  family                   = "${local.name_prefix}-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "beat"
      image     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
      essential = true
      command   = ["celery", "-A", "celery_app", "beat", "--loglevel=info"]

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
      ]

      secrets = [
        { name = "SYNC_DATABASE_URL", valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SYNC_DATABASE_URL::" },
        { name = "REDIS_URL",         valueFrom = "${data.aws_secretsmanager_secret.app.arn}:REDIS_URL::" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "beat"
        }
      }
    }
  ])
}

# ── ECS Services ──────────────────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "beat" {
  name            = "${local.name_prefix}-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = 1  # exactly one beat scheduler
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}
