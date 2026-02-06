/**
 * Production-Ready Terraform Configuration for ChatBot RAG Application
 * Includes: GKE Cluster, Redis, Load Balancing, Monitoring, and Security
 */

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
  }
  
  backend "gcs" {
    bucket = "btoproject-486405-486604-terraform-state"
    prefix = "chatbot-rag/state"
  }
}

# Local variables
locals {
  project_id = "btoproject-486405-486604"
  region     = "us-central1"
  zone       = "us-central1-a"
  environment = "production"
  
  labels = {
    environment = local.environment
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
    "compute.googleapis.com",
    "container.googleapis.com",
    "aiplatform.googleapis.com",
    "redis.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "storage-api.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "servicenetworking.googleapis.com",
  ])
  
  project = local.project_id
  service = each.key
  disable_on_destroy = false
}

# VPC Network
resource "google_compute_network" "vpc" {
  name                    = "chatbot-rag-vpc"
  auto_create_subnetworks = false
  project                 = local.project_id
  
  depends_on = [google_project_service.required_apis]
}

resource "google_compute_subnetwork" "gke_subnet" {
  name          = "gke-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = local.region
  network       = google_compute_network.vpc.name
  project       = local.project_id
  
  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.1.0.0/16"
  }
  
  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.2.0.0/16"
  }
  
  private_ip_google_access = true
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = "chatbot-rag-gke"
  location = local.zone
  project  = local.project_id
  
  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1
  
  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.gke_subnet.name
  
  # IP allocation for cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = "gke-pods"
    services_secondary_range_name = "gke-services"
  }
  
  # Workload Identity
  workload_identity_config {
    workload_pool = "${local.project_id}.svc.id.goog"
  }
  
  # Network policy
  network_policy {
    enabled = true
  }
  
  # Maintenance window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }
  }
  
  # Logging and monitoring
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }
  
  # Release channel for auto-upgrades
  release_channel {
    channel = "REGULAR"
  }
  
  # Security features
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
  
  resource_labels = local.labels
  
  depends_on = [
    google_project_service.required_apis,
    google_compute_subnetwork.gke_subnet
  ]
}

# GKE Node Pool
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = local.zone
  cluster    = google_container_cluster.primary.name
  node_count = 3
  project    = local.project_id
  
  # Auto-scaling
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }
  
  # Node management
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  node_config {
    preemptible  = false
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-standard"
    
    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    
    # OAuth scopes
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = local.labels
    
    tags = ["gke-node", "chatbot-rag"]
    
    metadata = {
      disable-legacy-endpoints = "true"
    }
    
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}

# Cloud Memorystore (Redis) for chat history
resource "google_redis_instance" "chat_history" {
  name           = "chatbot-chat-history"
  tier           = "STANDARD_HA"
  memory_size_gb = 5
  region         = local.region
  project        = local.project_id
  
  redis_version     = "REDIS_7_0"
  display_name      = "ChatBot Chat History Redis"
  reserved_ip_range = "10.3.0.0/29"
  
  authorized_network = google_compute_network.vpc.id
  
  labels = local.labels
  
  depends_on = [google_project_service.required_apis]
}

# Service Account for applications
resource "google_service_account" "app_sa" {
  account_id   = "chatbot-rag-app"
  display_name = "ChatBot RAG Application Service Account"
  project      = local.project_id
}

# IAM bindings for service account
resource "google_project_iam_member" "app_sa_roles" {
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
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}

# Workload Identity binding
resource "google_service_account_iam_binding" "workload_identity" {
  service_account_id = google_service_account.app_sa.name
  role               = "roles/iam.workloadIdentityUser"
  
  members = [
    "serviceAccount:${local.project_id}.svc.id.goog[default/chatbot-rag-backend]",
  ]
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

# Static IP for load balancer
resource "google_compute_global_address" "app_ip" {
  name    = "chatbot-rag-ip"
  project = local.project_id
}

# Cloud Storage bucket for Terraform state (if not exists)
resource "google_storage_bucket" "terraform_state" {
  name          = "${local.project_id}-terraform-state"
  location      = local.region
  project       = local.project_id
  force_destroy = false
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }
  
  uniform_bucket_level_access = true
  
  labels = local.labels
}

# Secret for JWT signing key
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "chatbot-jwt-secret"
  project   = local.project_id
  
  replication {
    automatic = true
  }
  
  labels = local.labels
}

resource "google_secret_manager_secret_version" "jwt_secret_version" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# Outputs
output "gke_cluster_name" {
  value       = google_container_cluster.primary.name
  description = "GKE cluster name"
}

output "gke_cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "GKE cluster endpoint"
  sensitive   = true
}

output "redis_host" {
  value       = google_redis_instance.chat_history.host
  description = "Redis instance host"
}

output "redis_port" {
  value       = google_redis_instance.chat_history.port
  description = "Redis instance port"
}

output "service_account_email" {
  value       = google_service_account.app_sa.email
  description = "Service account email for workload identity"
}

output "artifact_registry_url" {
  value       = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
  description = "Artifact Registry URL"
}

output "static_ip" {
  value       = google_compute_global_address.app_ip.address
  description = "Static IP address for load balancer"
}

output "gke_connect_command" {
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --zone=${local.zone} --project=${local.project_id}"
  description = "Command to connect to GKE cluster"
}
