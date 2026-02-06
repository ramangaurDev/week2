
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 5.0" }
  }
}

provider "google" {
  project = "btoproject-486405-486604"
  region  = "us-central1"
}

# Enable core services
resource "google_project_service" "services" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "cloudfunctions.googleapis.com",
  ])
  project = "btoproject-486405-486604"
  service = each.key
  disable_on_destroy = false
}

# Service account
resource "google_service_account" "rag" {
  account_id   = "rag-svc-ac"
  display_name = "RAG Service Account"
}

# IAM bindings
resource "google_project_iam_member" "roles" {
  for_each = {
    aiplatform_user   = "roles/aiplatform.user",
    vertex_viewer     = "roles/vertexai.viewer",
    storage_object    = "roles/storage.objectAdmin",
    secret_accessor   = "roles/secretmanager.secretAccessor",
  }
  project = "btoproject-486405-486604"
  role    = each.value
  member  = "serviceAccount:${google_service_account.rag.email}"
}

# Secret for JWT key
resource "google_secret_manager_secret" "jwt_key" {
  secret_id = "rag-jwt-key"
  replication { automatic = true }
}
resource "google_secret_manager_secret_version" "jwt_key_v" {
  secret      = google_secret_manager_secret.jwt_key.id
  secret_data = "change-me"
}
