#!/bin/bash
# Complete Deployment Script for ChatBot RAG Application
# Deploys both backend and frontend to GCP

set -e  # Exit on error

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration 
PROJECT_ID="${PROJECT_ID:-btoproject-486405-486604}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
ENVIRONMENT="${ENVIRONMENT:-production}"
GKE_CLUSTER="${GKE_CLUSTER:-chatbot-rag-gke}"

echo -e "${YELLOW}Retrieving credentials from GCP Secret Manager...${NC}"

# Get OAuth Client ID from Secret Manager
GOOGLE_CLIENT_ID=$(gcloud secrets versions access latest --secret=google-oauth-client-id 2>/dev/null || echo "")
if [ -z "$GOOGLE_CLIENT_ID" ]; then
  echo -e "${RED}Error: Could not retrieve OAuth Client ID from Secret Manager${NC}"
  echo -e "${YELLOW}Make sure you have access to Secret Manager and the secret exists${NC}"
  exit 1
fi

# Get Redis Host from Cloud Memorystore
REDIS_HOST=$(gcloud redis instances describe chatbot-chat-history --region=$REGION --format='value(host)' 2>/dev/null || echo "")
if [ -z "$REDIS_HOST" ]; then
  echo -e "${RED}Error: Could not get Redis host${NC}"
  exit 1
fi

REDIS_PORT="6379"

echo -e "${GREEN}✓ Credentials retrieved${NC}"
echo "  OAuth Client ID: ${GOOGLE_CLIENT_ID:0:20}..."
echo "  Redis Host: $REDIS_HOST"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ChatBot RAG - Complete Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Environment: $ENVIRONMENT"
echo ""

# Step 1: Set GCP project
echo -e "${YELLOW}Step 1: Setting GCP project...${NC}"
gcloud config set project $PROJECT_ID
echo -e "${GREEN}✓ Project set${NC}"
echo ""

# Step 2: Deploy infrastructure with Terraform
echo -e "${YELLOW}Step 2: Deploying infrastructure (Terraform)...${NC}"
cd infra/terraform

terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Export Redis connection details
export REDIS_HOST=$(terraform output -raw redis_host)
export REDIS_PORT=$(terraform output -raw redis_port)
export REDIS_PASSWORD=$(terraform output -raw redis_auth_string)
export FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)

echo -e "${GREEN}✓ Infrastructure deployed${NC}"
echo "  Redis Host: $REDIS_HOST"
echo "  Frontend Bucket: $FRONTEND_BUCKET"
echo ""

cd ../..

# Step 3: Create Kubernetes secrets
echo -e "${YELLOW}Step 3: Creating Kubernetes secrets...${NC}"

# Get GKE cluster credentials
gcloud container clusters get-credentials $GKE_CLUSTER \
  --zone=$ZONE \
  --project=$PROJECT_ID

# Create or update secrets with actual values
kubectl create secret generic app-secrets \
  --from-literal=redis_host=$REDIS_HOST \
  --from-literal=redis_port=$REDIS_PORT \
  --from-literal=redis_password="" \
  --from-literal=admin_emails="${ADMIN_EMAILS:-admin@example.com}" \
  --from-literal=google_client_ids="$GOOGLE_CLIENT_ID" \
  --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✓ Secrets created${NC}"
echo ""

# Step 4: Deploy backend to GKE
echo -e "${YELLOW}Step 4: Deploying backend to GKE...${NC}"

# Apply Kubernetes manifests
kubectl apply -f infra/kubernetes/configmap-secrets.yaml
kubectl apply -f infra/kubernetes/deployment.yaml

# Wait for rollout
kubectl rollout status deployment/chatbot-rag-backend --timeout=10m

echo -e "${GREEN}✓ Backend deployed${NC}"
echo ""

# Step 5: Build and deploy frontend
echo -e "${YELLOW}Step 5: Building and deploying frontend...${NC}"

cd frontend

# Install dependencies
npm ci

# Build production
npm run build:prod

# Get backend URL
BACKEND_URL=$(kubectl get service chatbot-rag-backend -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$BACKEND_URL" ]; then
  # If LoadBalancer not ready, get from ingress
  BACKEND_URL=$(kubectl get ingress chatbot-rag-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
fi

# Inject backend URL
echo "Backend URL: https://$BACKEND_URL"
find dist -name "*.js" -type f -exec sed -i \
  "s|https://chatbot-rag-api.example.com|https://$BACKEND_URL|g" {} +

# Deploy to Cloud Storage
gsutil -m rsync -r -c -d dist/chatbot-frontend/ gs://$FRONTEND_BUCKET/

# Set cache headers
gsutil -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" \
  "gs://$FRONTEND_BUCKET/*.js" \
  "gs://$FRONTEND_BUCKET/*.css"

gsutil setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" \
  "gs://$FRONTEND_BUCKET/index.html"

echo -e "${GREEN}✓ Frontend deployed${NC}"
echo ""

cd ..

# Step 6: Get deployment URLs
echo -e "${YELLOW}Step 6: Getting deployment URLs...${NC}"

FRONTEND_IP=$(terraform -chdir=infra/terraform output -raw frontend_ip_address)
BACKEND_IP=$(kubectl get ingress chatbot-rag-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Frontend URL: https://$FRONTEND_IP"
echo "Backend API URL: https://$BACKEND_IP"
echo ""
echo "Redis Host: $REDIS_HOST:$REDIS_PORT"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Configure DNS to point to frontend IP: $FRONTEND_IP"
echo "2. Wait for SSL certificate provisioning (15-30 minutes)"
echo "3. Update Google OAuth allowed origins"
echo "4. Test the application"
echo ""
echo -e "${GREEN}Happy deploying! 🚀${NC}"
