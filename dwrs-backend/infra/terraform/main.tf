# DWRS AWS Infrastructure — Terraform
# Region: ap-south-1 (Mumbai) — India data residency
# Run: terraform init && terraform plan -var-file="prod.tfvars"

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "dwrs-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "ap-south-1"
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region"   { default = "ap-south-1" }
variable "environment"  { default = "production" }
variable "db_password"  { sensitive = true }
variable "app_secret"   { sensitive = true }

# ── VPC ──────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "dwrs-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false  # HA: one per AZ in production

  tags = { Environment = var.environment, Project = "DWRS" }
}

# ── RDS PostgreSQL (Multi-AZ) ─────────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  identifier             = "dwrs-postgres-prod"
  engine                 = "postgres"
  engine_version         = "15.6"
  instance_class         = "db.t3.medium"
  allocated_storage      = 100
  max_allocated_storage  = 500
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.rds.arn

  db_name  = "dwrs_db"
  username = "dwrs_user"
  password = var.db_password

  multi_az               = true
  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = 30
  backup_window           = "02:00-03:00"
  maintenance_window      = "Mon:03:00-Mon:04:00"

  deletion_protection = true
  skip_final_snapshot = false

  tags = { Environment = var.environment }
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "dwrs-redis"
  description                   = "DWRS Session & Cache"
  node_type                     = "cache.t3.medium"
  num_cache_clusters            = 2
  automatic_failover_enabled    = true
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  subnet_group_name             = aws_elasticache_subnet_group.main.name
  security_group_ids            = [aws_security_group.redis.id]
}

# ── ECS Cluster (Fargate) ─────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "dwrs-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ── S3 Buckets ────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "photos" {
  bucket = "dwrs-worker-photos-${var.environment}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket                  = aws_s3_bucket.photos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── KMS Keys ─────────────────────────────────────────────────────────────────
resource "aws_kms_key" "rds" {
  description             = "DWRS RDS encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_key" "s3" {
  description             = "DWRS S3 encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

# ── WAF (Web Application Firewall) ────────────────────────────────────────────
resource "aws_wafv2_web_acl" "main" {
  name  = "dwrs-waf"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "dwrs-waf"
    sampled_requests_enabled   = true
  }
}

# ── CloudTrail (API audit) ────────────────────────────────────────────────────
resource "aws_cloudtrail" "main" {
  name                          = "dwrs-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail.id
  include_global_service_events = true
  is_multi_region_trail         = false
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }
}

# ── SNS Topic for security alerts ────────────────────────────────────────────
resource "aws_sns_topic" "security_alerts" {
  name              = "dwrs-security-alerts"
  kms_master_key_id = aws_kms_key.s3.arn
}

output "rds_endpoint"     { value = aws_db_instance.postgres.endpoint }
output "redis_endpoint"   { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "ecs_cluster_arn"  { value = aws_ecs_cluster.main.arn }
output "photos_bucket"    { value = aws_s3_bucket.photos.bucket }
