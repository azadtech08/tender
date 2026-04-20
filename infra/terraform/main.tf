terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — configure S3 + DynamoDB lock before first apply.
  # Uncomment and fill in after the S3 bucket + DynamoDB table are created.
  # backend "s3" {
  #   bucket         = "gem-terraform-state-ap-south-1"
  #   key            = "gem-saas/terraform.tfstate"
  #   region         = "ap-south-1"
  #   encrypt        = true
  #   dynamodb_table = "gem-terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  azs         = ["${var.aws_region}a", "${var.aws_region}b"]
}
