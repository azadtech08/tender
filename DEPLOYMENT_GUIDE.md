# 🚀 GeM Tender SaaS - Deployment Guide & Cloud Pricing

**Date:** April 24, 2026  
**Project:** GeM Tender SaaS  
**Stack:** FastAPI + Next.js + PostgreSQL + Redis + Celery

---

## 📋 Table of Contents

1. [Project Requirements](#project-requirements)
2. [Storage Architecture](#storage-architecture)
3. [Cloud Provider Comparison](#cloud-provider-comparison)
4. [Detailed Pricing Breakdown](#detailed-pricing-breakdown)
5. [AWS Deployment (Recommended)](#aws-deployment-recommended)
6. [Alternative Providers](#alternative-providers)
7. [Deployment Checklist](#deployment-checklist)
8. [Security Considerations](#security-considerations)

---

## 🔧 Project Requirements

### Architecture
- **Backend:** FastAPI (Python 3.12) + Uvicorn
- **Frontend:** Next.js 14 (TypeScript)
- **Database:** PostgreSQL 16
- **Cache:** Redis 7
- **Task Queue:** Celery + RabbitMQ/Redis
- **Worker:** Playwright-based PDF scraper
- **Containerization:** Docker (already configured)
- **IaC:** Terraform (AWS ap-south-1)

### Resource Needs (MVP Phase)
- API Service: 1-2 CPU cores, 512MB-1GB RAM
- Worker Service: 1 CPU core, 512MB RAM
- PostgreSQL: 10-20GB storage, burst performance OK
- Redis: 256MB-512MB RAM
- Frontend: Static site (minimal resources)

---

## � Storage Architecture

### 1. Database Storage (PostgreSQL)

#### MVP Phase
```
Database Size Estimation:
├─ Tenders Table (initial): ~2-5 MB (1,000s of records)
├─ Jobs Table: ~1-2 MB
├─ Vendors Table: ~500 KB
├─ Tender Items: ~3-5 MB
├─ Audit Logs: ~2-3 MB
├─ User Data & Auth: ~1 MB
├─ Indices & Overhead: ~2-3 MB
├─ TOTAL: 15-20 GB (including space for growth)
└─ Backup (1 monthly full + 4 weekly): ~80 GB total
```

**Cost (AWS RDS):**
- db.t3.micro: 20GB gp2 SSD = **$35/month**
- Backup storage: ~80GB = **$8/month** (after 1 free backup)
- **Total: $43/month**

#### Production Phase
```
Projected Database Size (Year 1):
├─ 10,000+ tenders: ~30-40 MB
├─ 100,000+ jobs: ~15-20 MB
├─ Vendor network: ~5-10 MB
├─ Full text search indices: ~50-100 MB
├─ Audit/analytics data: ~30-50 MB
├─ User-generated content: ~20-30 MB
├─ TOTAL: 150-250 GB
└─ With backups (daily + weekly + monthly): ~1.5 TB
```

**Cost (AWS RDS):**
- db.t3.small/medium: 100GB gp3 SSD = **$70-100/month**
- Backup storage: ~1.5TB = **$50-70/month**
- **Total: $120-170/month**

---

### 2. File Storage (PDFs & Documents)

#### What's Stored
```
PDF Storage Breakdown:
├─ Tender PDFs (avg 500KB per document): 
│  └─ 1,000 tenders × 500KB = 500 GB (MVP year)
├─ Contract PDFs (avg 1MB per document):
│  └─ 500 contracts × 1MB = 500 GB
├─ Extracted data/thumbnails (1 per PDF):
│  └─ 1,500 files × 100KB = 150 GB
├─ Processed archives (compressed monthly):
│  └─ ~100 GB/month × 12 = 1.2 TB
└─ TOTAL: ~2.3 TB per year
```

#### Storage Options

**Option A: AWS S3 (Recommended)**
```
Costs:
├─ Standard Storage: $0.023/GB/month
│  └─ 500GB × $0.023 = $11.50/month
├─ Intelligent Tiering: $0.0125/GB/month
│  └─ Automatically archives old files
│  └─ 500GB × $0.0125 = $6.25/month
├─ Glacier (cold archive): $0.004/GB/month
│  └─ For annual backups
│  └─ 1.2TB × $0.004 = $4.80/month
├─ Data Transfer OUT: $0.09/GB
│  └─ ~100GB/month downloads = $9/month
└─ TOTAL S3: $30-40/month (MVP)
```

**Option B: Cloudflare R2 (Cost-Effective)**
```
Costs:
├─ Storage: $0.015/GB/month
│  └─ 500GB × $0.015 = $7.50/month
├─ Download: $0.02/GB (no free tier, but cheap)
│  └─ ~100GB/month = $2/month
├─ API calls: Included
└─ TOTAL R2: $9.50/month (MVP) - Much cheaper!
```

**Option C: DigitalOcean Spaces**
```
Costs:
├─ 250GB base: $5/month
├─ Additional storage: $0.02/GB
│  └─ 250GB × $0.02 = $5/month additional
├─ Bandwidth: $0.02/GB
│  └─ 100GB/month = $2/month
└─ TOTAL Spaces: $12/month (MVP)
```

---

### 3. Redis Cache Storage

#### MVP Phase
```
Redis Memory Usage:
├─ Session cache (1,000 active users × 1KB): ~1 MB
├─ Job queue data: ~10-20 MB
├─ Search results cache: ~5-10 MB
├─ Rate limit buckets: ~2 MB
├─ Temporary computations: ~10 MB
└─ TOTAL: ~30-50 MB required (128MB recommended for headroom)
```

**Cost (AWS ElastiCache):**
- cache.t3.micro: $25/month

#### Production Phase
```
Redis Memory Usage:
├─ 10,000+ active user sessions: ~10-50 MB
├─ Large job queues: ~50-100 MB
├─ Cache warmed data: ~100-200 MB
├─ Rate limiting: ~10 MB
└─ TOTAL: ~200-400 MB required
```

**Cost (AWS ElastiCache):**
- cache.t3.small: $50-70/month
- Cluster mode (high availability): ~$100-150/month

---

### 4. Backup Storage

#### AWS Native Backups
```
Automated Backup Schedule:
├─ Daily snapshots: 7 days retention = 7 × 20GB = 140 GB
├─ Weekly snapshots: 4 weeks = 4 × 20GB = 80 GB
├─ Monthly snapshots: 12 months = 12 × 20GB = 240 GB
├─ RDS snapshot storage: $0.095/GB/month
│  └─ 460 GB × $0.095 = $43.70/month
└─ S3 backup exports: ~$30/month for object storage
```

#### Cross-Region Disaster Recovery
```
Multi-Region Setup (Optional):
├─ Secondary RDS (read replica): +$70/month
├─ S3 cross-region replication: +$10-15/month
└─ TOTAL DR: +$85/month (Production only)
```

---

### 5. Application Logs & Monitoring

#### Log Storage (CloudWatch/ELK)
```
MVP Log Volume:
├─ API logs: ~100 MB/day
├─ Worker logs: ~50 MB/day
├─ Database logs: ~20 MB/day
├─ Access logs: ~30 MB/day
└─ TOTAL: ~200 MB/day = ~6 GB/month

AWS CloudWatch:
├─ Log ingestion: $0.50/GB = $3/month
├─ Log storage: $0.03/GB/month = $0.18/month
├─ TOTAL: $3.18/month (MVP)
```

#### Production Log Volume
```
├─ All logs: ~500 MB/day = ~15 GB/month
├─ AWS CloudWatch: $7-8/month
└─ Or ELK Stack (self-hosted): ~$30-50/month
```

---

### 6. Total Storage Costs by Provider

#### AWS (Recommended for India)
```
MVP Setup:
├─ PostgreSQL RDS (20GB): $35
├─ Backup storage: $8
├─ S3 (500GB PDFs): $12-15
├─ CloudWatch logs: $3
└─ TOTAL STORAGE: $58-61/month

Production Setup (Year 1):
├─ PostgreSQL RDS (100GB): $70-100
├─ Backup storage: $50-70
├─ S3 (2TB PDFs): $40-50
├─ CloudWatch logs: $8-10
├─ Glacier archives: $5
└─ TOTAL STORAGE: $173-235/month
```

#### DigitalOcean
```
MVP Setup:
├─ PostgreSQL (25GB): $15
├─ Backups (managed): +$7
├─ Spaces (250GB base): $5
├─ Additional storage: +$5
└─ TOTAL: $32/month (CHEAPEST)

Production Setup:
├─ PostgreSQL (100GB + HA): $90
├─ Spaces (500GB): $15
└─ TOTAL: $105/month
```

#### Cloudflare R2 (Best for PDFs)
```
If using R2 for file storage:
├─ 500GB storage: $7.50
├─ Data transfer: $2-3
├─ Total: $10-11/month (cheapest file storage!)
```

---

### 7. Storage Growth Projection (5-Year)

```
Year 1: 500 GB (PDFs) + 20 GB (DB) = 520 GB total
Year 2: 1.0 TB (PDFs) + 50 GB (DB) = 1.05 TB
Year 3: 1.5 TB (PDFs) + 100 GB (DB) = 1.6 TB
Year 4: 2.2 TB (PDFs) + 150 GB (DB) = 2.35 TB
Year 5: 3.0 TB (PDFs) + 250 GB (DB) = 3.25 TB

Cost Implications:
├─ Year 1 S3: ~$60/month
├─ Year 2 S3: ~$100/month
├─ Year 3 S3: ~$140/month
├─ Year 4 S3: ~$180/month
└─ Year 5 S3: ~$200+/month

Consider:
└─ Implement tiered storage (hot/warm/cold)
└─ Archive old PDFs to Glacier ($0.004/GB)
└─ Delete old temporary files monthly
```

---

### 8. Storage Optimization Tips

#### Database Optimization
```sql
-- Add indices for frequently searched columns
CREATE INDEX idx_tenders_status ON tenders(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE INDEX idx_vendors_city ON vendors(city);

-- Archive old audit logs quarterly
DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '1 year';

-- Analyze table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### File Storage Optimization
```
1. Compress PDFs before storing
   - Use ghostscript: gs -sDEVICE=pdfwrite -q -o output.pdf input.pdf
   - Typical compression: 60-70% smaller

2. Generate thumbnails for previews
   - 100KB thumbnails instead of full PDFs
   - Serve from CDN cache

3. Use smart tiering
   - S3 Intelligent-Tiering: auto-archive after 30 days of no access
   - Glacier: archive after 90 days ($0.004 vs $0.023/GB)

4. Delete old extracts monthly
   - Keep only latest 3 versions of extracted data
   - Delete temporary working files

5. Implement CDN caching
   - CloudFront (AWS): $0.085/GB (cheaper than S3 egress)
   - Cache PDFs for 30 days
```

#### Redis Optimization
```
- Set TTL on all cache entries
- Implement cache eviction policy: allkeys-lru
- Monitor memory usage with MEMORY STATS
- Archive large job results to S3
```

---



### Quick Pricing Overview

| Provider | MVP Cost/mo (incl. storage) | Production Cost/mo (incl. storage) | India Region | Data Residency | DevOps Complexity |
|----------|-------------|------------------|--------------|-----------------|-------------------|
| **AWS** | $180-190 | $550-600 | ✅ ap-south-1 | ✅ Yes | High |
| **DigitalOcean** | $84 | $244 | ✅ Bangalore | ✅ Yes | Medium |
| **Hetzner** | $50-70 | $150-180 | ❌ No | ❌ No | Medium-High |
| **Render** | $70-80 | $250+ | ❌ No | ❌ No | Low |
| **Railway** | $60-100 | $180-250 | ❌ No | ❌ No | Low |
| **Linode (Akamai)** | $110-130 | $200-250 | ✅ Mumbai | ✅ Yes | Medium |

---

## 💰 Detailed Pricing Breakdown

### 1. AWS (Recommended for India Compliance)

#### MVP Setup ($115-120/month)
```
ECS Fargate - API Container
├─ Task Definition: 0.25 CPU, 512MB RAM (t3.small equivalent)
├─ Number of tasks: 1-2
├─ Monthly cost: $15-30

ECS Fargate - Worker Container
├─ Task Definition: 0.25 CPU, 512MB RAM
├─ Number of tasks: 1
├─ Monthly cost: $15

RDS PostgreSQL (Database)
├─ Instance: db.t3.micro
├─ Storage: 20GB (includes backups)
├─ Multi-AZ: No
├─ Monthly cost: $35

PostgreSQL Storage Breakdown:
├─ Database storage (gp2 SSD): 20GB @ $0.10/GB = $2/month
├─ Backup storage: ~80GB @ $0.095/GB = $7.60/month
└─ Subtotal: $45/month

ElastiCache Redis
├─ Node type: cache.t3.micro
├─ Storage: 0.5GB
├─ Monthly cost: $25

S3 Storage (PDFs, Documents)
├─ Storage: 500GB @ $0.023/GB/month = $11.50/month
├─ Data transfer (100GB): @ $0.09/GB = $9/month
├─ Monthly cost: $20.50

CloudWatch Logs & Monitoring
├─ Log ingestion: ~6GB/month @ $0.50/GB = $3/month
├─ Log storage: $1/month
├─ Monthly cost: $4

Application Load Balancer (ALB)
├─ Number of ALBs: 1
├─ Monthly cost: $20

CloudFront CDN (Frontend)
├─ Data transfer: ~5GB/month
├─ Monthly cost: $5

Data Transfer (Outbound)
├─ Est. 10GB/month international
├─ Monthly cost: $1-2

TOTAL: $180-190/month (includes storage)
Free Tier Coverage: -$0 (after 12 months)
```

#### Production Setup ($200-220/month)
```
ECS Fargate - API Container (Auto-scaling)
├─ Task Definition: 0.5 CPU, 1GB RAM (t3.small)
├─ Min tasks: 2, Max: 6
├─ Monthly cost: $30-40

ECS Fargate - Worker Container
├─ Task Definition: 0.5 CPU, 1GB RAM
├─ Min tasks: 2, Max: 4
├─ Monthly cost: $30

RDS PostgreSQL (High Availability)
├─ Instance: db.t3.small
├─ Storage: 50GB
├─ Multi-AZ: Yes (+50% cost)
├─ Backups: Automated daily
├─ Monthly cost: $70

RDS Storage Breakdown:
├─ Database storage (gp3 SSD): 100GB @ $0.10/GB = $10/month
├─ Backup storage: ~1.5TB @ $0.095/GB = $142.50/month
├─ Multi-AZ premium: +50% = $75/month
└─ Subtotal: $227.50/month

ElastiCache Redis (Cluster)
├─ Node type: cache.t3.small
├─ Num nodes: 2 (replication)
├─ Monthly cost: $50

S3 Storage (PDFs, Documents)
├─ Storage: 2TB @ $0.023/GB/month = $46/month
├─ Data transfer (200GB): @ $0.09/GB = $18/month
├─ Glacier archives (1TB): @ $0.004/GB = $4/month
├─ Monthly cost: $68

CloudWatch Logs & Monitoring
├─ Log ingestion: ~15GB/month @ $0.50/GB = $7.50/month
├─ Log storage + analysis: $3/month
├─ Application monitoring: $5/month
├─ Monthly cost: $15.50

Application Load Balancer
├─ Monthly cost: $20

CloudFront CDN
├─ Data transfer: ~20GB/month
├─ Monthly cost: $10

Additional (Monitoring, S3, etc.)
├─ CloudWatch alarms: $5
├─ S3 cross-region replication: $10
├─ Monthly cost: $15

TOTAL: $550-600/month (includes all storage + DR)
```

**Why costs increased significantly:**
- Multi-AZ RDS backup storage: $142/month (must for production)
- Larger database and PDF storage
- Disaster recovery setup
- Enhanced monitoring and alerting

**Why AWS?**
- ✅ Data hosted in India (ap-south-1/Mumbai)
- ✅ Compliant with Indian data residency laws
- ✅ Terraform already configured
- ✅ Auto-scaling & high availability
- ✅ RDS managed backups
- ✅ 12-month free tier (if new account)

**Drawbacks:**
- Steeper learning curve
- Requires AWS credentials management
- More complex pricing tiers

---

### 2. DigitalOcean (Budget-Friendly, India-Compliant)

#### MVP Setup ($64/month)
```
Droplets (VPS)
├─ API Droplet: Basic ($6/mo) - 1GB RAM, 1 vCPU
├─ Worker Droplet: Basic ($6/mo)
├─ Subtotal: $12

Managed PostgreSQL
├─ Single node, 1GB RAM, 25GB SSD
├─ Automatic backups (~50GB storage)
├─ Monthly cost: $15

Managed Redis
├─ Single node, 256MB RAM
├─ Monthly cost: $15

Spaces Object Storage (PDFs)
├─ 250GB base storage included: $5
├─ Additional storage (250GB): 250GB @ $0.02/GB = $5
├─ Data transfer (100GB/month): @ $0.02/GB = $2
├─ Monthly cost: $12

Load Balancer
├─ Monthly cost: $10

App Platform (Next.js Frontend)
├─ Static site hosting
├─ Monthly cost: $12

Monitoring & Backups
├─ Additional reserves: $8

TOTAL: $84/month (includes 500GB file storage!)
```

#### Production Setup ($150+/month)
```
Droplets
├─ API: General Purpose ($18/mo) - 4GB RAM
├─ Worker: ($12/mo) - 2GB RAM
├─ Subtotal: $30

Managed PostgreSQL
├─ Premium ($45/mo) - 4GB RAM, 100GB SSD
├─ HA setup with replica ($45/mo)
├─ Backup storage (~300GB): $25/mo
├─ Subtotal: $115

Managed Redis
├─ Premium ($45/mo) - 1GB RAM

Spaces Object Storage (PDFs)
├─ 2TB storage: 2000GB @ $0.02/GB = $40/mo
├─ Data transfer (200GB): @ $0.02/GB = $4/mo
├─ Monthly cost: $44

Load Balancer: $10

TOTAL: $244/month (includes all storage)
```

**Why DigitalOcean?**
- ✅ Very affordable ($64 MVP start)
- ✅ India region available (Bangalore)
- ✅ Simple, intuitive interface
- ✅ Transparent, fixed pricing
- ✅ Great documentation

**Drawbacks:**
- Limited auto-scaling
- No built-in Terraform support (compared to AWS)
- Less suitable for massive scale

---

### 3. Linode/Akamai (India Region + Affordable)

#### MVP Setup ($80-100/month)
```
Linode Instances (Nanode 1GB)
├─ API: Nanode 1GB ($5/mo) - 1 vCPU, 1GB RAM
├─ Worker: Nanode 1GB ($5/mo)
├─ Subtotal: $10

Managed PostgreSQL
├─ Small instance: $15/mo

Managed Redis
├─ Small instance: $10/mo

NodeBalancer (Load Balancer)
├─ Monthly cost: $20

Object Storage
├─ 250GB + traffic: $5

Domain + SSL: Free (Let's Encrypt)

TOTAL: $85/month
```

**Why Linode?**
- ✅ Mumbai datacenter (India)
- ✅ Affordable pricing
- ✅ Good free tier
- ✅ Terraform support

**Drawbacks:**
- Smaller ecosystem than AWS/DO
- Fewer managed services

---

## 🚀 AWS Deployment (Recommended)

### Prerequisites
```bash
# Install required tools
brew install terraform aws-cli  # macOS
# or use Windows installers for Terraform + AWS CLI

# Configure AWS credentials
aws configure
# Enter:
# - Access Key ID
# - Secret Access Key
# - Region: ap-south-1
# - Output format: json
```

### Step-by-Step Deployment

#### 1. Initialize Terraform
```bash
cd infra/terraform
terraform init

# Configure backend for state management
# Uncomment backend "s3" block in main.tf after creating S3 bucket
```

#### 2. Review Infrastructure Plan
```bash
terraform plan -var="environment=staging"
```

#### 3. Deploy to AWS
```bash
terraform apply -var="environment=staging"

# Outputs will show:
# - ALB DNS name
# - RDS endpoint
# - ElastiCache endpoint
```

#### 4. Build & Push Docker Images
```bash
# Build and push to ECR
aws ecr get-login-password --region ap-south-1 | docker login \
  --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com

docker build -t gem-api:latest -f apps/api/Dockerfile .
docker tag gem-api:latest <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/gem-api:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/gem-api:latest
```

#### 5. Deploy Services
```bash
# Update ECS services with new image
aws ecs update-service \
  --cluster gem-staging \
  --service gem-api \
  --force-new-deployment \
  --region ap-south-1
```

---

## 🔐 Security Considerations

### Before Going Live

- [ ] **SSL/TLS Certificates**
  - Use AWS Certificate Manager (free)
  - Configure HTTPS only
  
- [ ] **Database Security**
  - Enable encryption at rest (RDS)
  - Enable encryption in transit
  - Restrict security group to API only
  - Daily automated backups
  
- [ ] **Application Security**
  - Environment variables in AWS Secrets Manager
  - API rate limiting
  - CORS properly configured
  - SQL injection prevention (SQLAlchemy ORM)
  
- [ ] **Monitoring & Logging**
  - CloudWatch for logs
  - Set up alerts for:
    - High CPU usage
    - Database connection issues
    - Failed deployments
  
- [ ] **Data Residency (India Compliance)**
  - Verify all data stored in ap-south-1
  - No data replication outside India
  - Document for compliance audit

---

## ✅ Deployment Checklist

### Pre-Deployment
- [ ] All code committed and tested
- [ ] Environment variables configured
- [ ] Database migrations ready
- [ ] SSL certificates obtained
- [ ] Domain DNS configured
- [ ] Backup strategy documented

### Infrastructure Setup
- [ ] Cloud provider account created
- [ ] Terraform infrastructure deployed
- [ ] Database created and migrated
- [ ] Redis cluster running
- [ ] Load balancer configured

### Application Deployment
- [ ] Docker images built
- [ ] Images pushed to registry (ECR/Docker Hub)
- [ ] Container orchestration running (ECS/Kubernetes)
- [ ] Environment variables set
- [ ] Health checks passing

### Post-Deployment
- [ ] Access application via domain
- [ ] API endpoints responding
- [ ] Database connectivity verified
- [ ] Celery workers running
- [ ] Monitoring alerts active
- [ ] Backups scheduled

### Security & Compliance
- [ ] SSL certificate installed
- [ ] Firewall rules configured
- [ ] CORS headers correct
- [ ] Database encrypted
- [ ] Logs being collected
- [ ] India data residency verified

---

## 📞 Recommended Decision Tree

```
Are you in India and need data residency?
├─ YES
│  ├─ Budget < $100/mo? → DigitalOcean Bangalore
│  ├─ Budget $100-150/mo? → AWS ap-south-1 (RECOMMENDED)
│  └─ Budget < $50/mo? → Linode Mumbai
│
└─ NO (Global users OK)
   ├─ Want simplest setup? → Render or Railway
   ├─ Want cheapest? → Hetzner (EU datacenter)
   └─ Want most control? → DigitalOcean or Linode
```

---

## 🎯 Final Recommendation

### **Best Choice: AWS (ap-south-1)**

**Why:**
1. You already have Terraform configured for AWS
2. India region ensures data residency compliance
3. Comprehensive storage solutions (S3, Glacier, backups)
4. Auto-scaling from $180/mo (MVP) to $550+/mo (production)
5. 12-month free tier available for new accounts
6. Managed RDS backups with disaster recovery

**Storage Strategy:**
- PostgreSQL RDS: Automated daily backups + Multi-AZ replication
- PDFs: S3 Standard → Intelligent-Tiering → Glacier archival
- Archives: Long-term retention in Glacier ($0.004/GB)
- Total Year 1 storage: ~520GB, growing to 3TB by Year 5

**Next Steps:**
1. Create AWS account
2. Apply Terraform configuration
3. Set up automated backup strategy
4. Implement S3 tiered storage policies
5. Configure CloudFront CDN for PDF delivery
6. Set up CI/CD (GitHub Actions)
7. Deploy application
8. Monitor and scale as needed

### **Budget Alternative: DigitalOcean** (includes 500GB storage base)
- **MVP: $84/month** (cheapest for startups)
- **Production: $244/month** (2TB storage included)
- Great for India-based operations (Bangalore region)
- Simpler UI, transparent pricing
- Good for teams wanting less DevOps overhead

---

**Document Version:** 2.0 (Storage-Enhanced)  
**Last Updated:** April 24, 2026  
**Contact:** For deployment support, refer to DevOps team

---

## 📚 Additional Resources

### Storage & Backup Documentation
- **AWS S3 Storage Classes:** https://aws.amazon.com/s3/storage-classes/
- **AWS Glacier:** https://aws.amazon.com/glacier/
- **PostgreSQL Backup Strategies:** https://www.postgresql.org/docs/current/backup.html
- **RDS Backup & Restore:** https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html

### Deployment & Infrastructure
- **AWS Documentation:** https://docs.aws.amazon.com/
- **Terraform AWS Provider:** https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **FastAPI Deployment:** https://fastapi.tiangolo.com/deployment/
- **Next.js Production:** https://nextjs.org/docs/going-to-production

### Cost Management
- **AWS Cost Calculator:** https://calculator.aws/
- **AWS Pricing Pages:** https://aws.amazon.com/pricing/
- **DigitalOcean Pricing:** https://www.digitalocean.com/pricing/
- **AWS Cost Explorer:** https://console.aws.amazon.com/cost-management/

### Monitoring & Optimization
- **CloudWatch Monitoring:** https://docs.aws.amazon.com/cloudwatch/
- **Database Performance Insights:** https://aws.amazon.com/rds/performance-insights/
- **S3 Storage Lens:** https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-lens.html

---

## ⚡ Quick Storage Command Reference

### PostgreSQL Management
```bash
# Connect to RDS PostgreSQL
psql -h <RDS_ENDPOINT> -U gem -d gem_tender

# Check table sizes
\dt+ 

# Find largest tables
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Create backup
pg_dump -h <RDS_ENDPOINT> -U gem gem_tender > backup.sql

# Restore backup
psql -h <RDS_ENDPOINT> -U gem gem_tender < backup.sql
```

### S3 Management
```bash
# List S3 buckets
aws s3 ls

# Upload PDFs to S3
aws s3 sync ./pdfs s3://gem-tender-dev/pdfs/ --acl private

# Check S3 bucket size
aws s3api list-objects-v2 --bucket gem-tender-dev --query 'Contents[].Size' --output text | awk '{sum+=$1} END {print sum/1024/1024/1024 " GB"}'

# Archive to Glacier
aws s3api put-object-acl --bucket gem-tender-dev --key archive_2024.tar.gz --storage-class GLACIER
```

### Monitoring Storage
```bash
# CloudWatch: Get storage metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DBInstanceStorageUsed \
  --dimensions Name=DBInstanceIdentifier,Value=gem-tender-db \
  --start-time 2024-04-01T00:00:00Z \
  --end-time 2024-04-24T00:00:00Z \
  --period 86400 \
  --statistics Average
```

---

**Happy Deploying! 🚀**