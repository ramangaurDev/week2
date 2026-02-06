/**
 * Terraform Configuration for Cloud Run Deployment
 * Deploys both Frontend (Angular) and Backend (FastAPI) as separate Cloud Run services
 */

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

locals {
  project_id = "btoproject-486405-486604"
  region     = "us-central1"
  
  labels = {
    environment = "production"
    application = "chatbot-rag"
    managed-by  = "terraform"
  }
}

provider "google" {
  project = local.project_id
  region  = local.region
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "redis.googleapis.com",
    "storage-api.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
  ])
  
  project            = local.project_id
  service            = each.key
  disable_on_destroy = false
}

# VPC Connector for Cloud Run to access Redis
resource "google_vpc_access_connector" "connector" {
  name          = "chatbot-rag-connector"
  region        = local.region
  ip_cidr_range = "10.8.0.0/28"
  network       = "default"
  
  depends_on = [google_project_service.required_apis]
}

# Cloud Memorystore Redis for chat history
resource "google_redis_instance" "chat_history" {
  name               = "chatbot-chat-history"
  tier               = "STANDARD_HA"
  memory_size_gb     = 5
  region             = local.region
  redis_version      = "REDIS_7_0"
  display_name       = "ChatBot Chat History Redis"
  
  authorized_network = "default"
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

# Service Account for Backend
resource "google_service_account" "backend_sa" {
  account_id   = "chatbot-rag-backend"
  display_name = "ChatBot RAG Backend Service Account"
  project      = local.project_id
}

# IAM roles for Backend service account
resource "google_project_iam_member" "backend_sa_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
    "roles/datastore.user",
  ])
  
  project = local.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.backend_sa.email}"
}

# Service Account for Frontend (minimal permissions)
resource "google_service_account" "frontend_sa" {
  account_id   = "chatbot-rag-frontend"
  display_name = "ChatBot RAG Frontend Service Account"
  project      = local.project_id
}

# IAM roles for Frontend service account
resource "google_project_iam_member" "frontend_sa_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
  
  project = local.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.frontend_sa.email}"
}

# Artifact Registry for container images
resource "google_artifact_registry_repository" "docker_repo" {
  location      = local.region
  repository_id = "chatbot-rag-images"
  description   = "Docker repository for ChatBot RAG application"
  format        = "DOCKER"
  project       = local.project_id
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

# Secret for JWT signing key
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "chatbot-jwt-secret"
  project   = local.project_id
  
  replication {
    automatic = true
  }
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "jwt_secret_version" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# Secret for Google OAuth Client ID
resource "google_secret_manager_secret" "google_oauth_client_id" {
  secret_id = "google-oauth-client-id"
  project   = local.project_id
  
  replication {
    automatic = true
  }
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

# Secret for Google OAuth Client Secret
resource "google_secret_manager_secret" "google_oauth_client_secret" {
  secret_id = "google-oauth-client-secret"
  project   = local.project_id
  
  replication {
    automatic = true
  }
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

# GCS Bucket for documents
resource "google_storage_bucket" "documents" {
  name          = "${local.project_id}-rag-documents"
  location      = local.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  labels = local.labels
}

# Cloud Run Backend Service
resource "google_cloud_run_service" "backend" {
  name     = "chatbot-rag-backend"
  location = local.region
  project  = local.project_id
  
  template {
    spec {
      service_account_name = google_service_account.backend_sa.email
      
      containers {
        image = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}/backend:latest"
        
        ports {
          container_port = 8080
        }
        
        resources {
          limits = {
            cpu    = "2000m"
            memory = "2Gi"
          }
        }
        
        env {
          name  = "PROJECT_ID"
          value = local.project_id
        }
        
        env {
          name  = "REGION"
          value = local.region
        }
        
        env {
          name  = "ENVIRONMENT"
          value = "production"
        }
        
        env {
          name  = "VERTEX_LOCATION"
          value = local.region
        }
        
        env {
          name  = "MODEL_VARIANT"
          value = "gemini-2.0-flash-001"
        }
        
        env {
          name  = "EMBEDDING_MODEL"
          value = "text-embedding-004"
        }
        
        env {
          name  = "REDIS_HOST"
          value = google_redis_instance.chat_history.host
        }
        
        env {
          name  = "REDIS_PORT"
          value = tostring(google_redis_instance.chat_history.port)
        }
        
        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.documents.name
        }
        
        env {
          name  = "FIRESTORE_COLLECTION"
          value = "rag_chunks"
        }
        
        env {
          name  = "USE_FIRESTORE"
          value = "true"
        }
        
        env {
          name  = "LOG_LEVEL"
          value = "INFO"
        }
        
        env {
          name  = "MAX_TOKENS"
          value = "8000"
        }
        
        env {
          name = "ADMIN_EMAILS"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.jwt_secret.secret_id
              key  = "latest"
            }
          }
        }
      }
    }
    
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale"      = "1"
        "autoscaling.knative.dev/maxScale"      = "10"
        "run.googleapis.com/vpc-access-connector" = google_vpc_access_connector.connector.id
        "run.googleapis.com/vpc-access-egress"    = "all-traffic"
      }
      
      labels = local.labels
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
  
  depends_on = [
    google_project_service.required_apis,
    google_vpc_access_connector.connector
  ]
}

# Cloud Run Frontend Service
resource "google_cloud_run_service" "frontend" {
  name     = "chatbot-rag-frontend"
  location = local.region
  project  = local.project_id
  
  template {
    spec {
      service_account_name = google_service_account.frontend_sa.email
      
      containers {
        image = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}/frontend:latest"
        
        ports {
          container_port = 80
        }
        
        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }
        
        env {
          name  = "API_URL"
          value = google_cloud_run_service.backend.status[0].url
        }
        
        env {
          name  = "ENVIRONMENT"
          value = "production"
        }
      }
    }
    
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "0"
        "autoscaling.knative.dev/maxScale" = "5"
      }
      
      labels = local.labels
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
  
  depends_on = [
    google_project_service.required_apis,
    google_cloud_run_service.backend
  ]
}

# IAM policy to allow unauthenticated access to frontend
resource "google_cloud_run_service_iam_member" "frontend_public" {
  service  = google_cloud_run_service.frontend.name
  location = google_cloud_run_service.frontend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# IAM policy to allow unauthenticated access to backend (or restrict as needed)
resource "google_cloud_run_service_iam_member" "backend_public" {
  service  = google_cloud_run_service.backend.name
  location = google_cloud_run_service.backend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Outputs
output "backend_url" {
  value       = google_cloud_run_service.backend.status[0].url
  description = "Backend Cloud Run service URL"
}

output "frontend_url" {
  value       = google_cloud_run_service.frontend.status[0].url
  description = "Frontend Cloud Run service URL"
}

output "redis_host" {
  value       = google_redis_instance.chat_history.host
  description = "Redis instance host IP"
}

output "redis_port" {
  value       = google_redis_instance.chat_history.port
  description = "Redis instance port"
}

output "backend_service_account" {
  value       = google_service_account.backend_sa.email
  description = "Backend service account email"
}

output "frontend_service_account" {
  value       = google_service_account.frontend_sa.email
  description = "Frontend service account email"
}

output "artifact_registry_url" {
  value       = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
  description = "Artifact Registry URL for pushing images"
}

output "documents_bucket" {
  value       = google_storage_bucket.documents.name
  description = "GCS bucket for document storage"
}

output "vpc_connector_name" {
  value       = google_vpc_access_connector.connector.name
  description = "VPC connector name"
}
