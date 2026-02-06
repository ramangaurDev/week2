# Cloud Memorystore (Redis) for Chat History
# This file provisions a Redis instance for storing chat sessions and history

resource "google_redis_instance" "chat_history" {
  name               = "${var.project_name}-redis-${var.environment}"
  display_name       = "ChatBot RAG - Chat History"
  tier               = var.redis_tier
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  project            = var.project_id
  
  # High availability configuration
  replica_count      = var.redis_replica_count
  read_replicas_mode = var.redis_replica_count > 0 ? "READ_REPLICAS_ENABLED" : null
  
  # Version and features
  redis_version      = "REDIS_7_0"
  auth_enabled       = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"
  
  # Networking - Connect to GKE VPC
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  
  # Maintenance window (Sunday 2-4 AM)
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 2
        minutes = 0
        seconds = 0
        nanos   = 0
      }
    }
  }
  
  # Redis configuration
  redis_configs = {
    "maxmemory-policy"  = "allkeys-lru"  # Evict least recently used keys
    "notify-keyspace-events" = "Ex"      # Enable keyspace notifications
    "timeout"           = "300"          # Connection timeout (5 min)
  }
  
  labels = {
    environment = var.environment
    app         = "chatbot-rag"
    component   = "redis"
    managed_by  = "terraform"
  }
}

# Output Redis connection details
output "redis_host" {
  description = "Redis instance host address"
  value       = google_redis_instance.chat_history.host
  sensitive   = false
}

output "redis_port" {
  description = "Redis instance port"
  value       = google_redis_instance.chat_history.port
  sensitive   = false
}

output "redis_auth_string" {
  description = "Redis AUTH string (password)"
  value       = google_redis_instance.chat_history.auth_string
  sensitive   = true
}

output "redis_connection_string" {
  description = "Full Redis connection string"
  value       = "redis://:${google_redis_instance.chat_history.auth_string}@${google_redis_instance.chat_history.host}:${google_redis_instance.chat_history.port}/0"
  sensitive   = true
}

# Variables for Redis configuration
variable "redis_tier" {
  description = "Redis service tier (BASIC or STANDARD_HA)"
  type        = string
  default     = "STANDARD_HA"  # High availability with automatic failover
}

variable "redis_memory_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 5  # 5GB should handle ~1M chat sessions
}

variable "redis_replica_count" {
  description = "Number of read replicas (0-5)"
  type        = number
  default     = 1  # One read replica for HA
}

# Secret Manager secret for Redis connection
resource "google_secret_manager_secret" "redis_host" {
  secret_id = "redis-host"
  project   = var.project_id
  
  replication {
    auto {}
  }
  
  labels = {
    app = "chatbot-rag"
  }
}

resource "google_secret_manager_secret_version" "redis_host" {
  secret      = google_secret_manager_secret.redis_host.id
  secret_data = google_redis_instance.chat_history.host
}

resource "google_secret_manager_secret" "redis_port" {
  secret_id = "redis-port"
  project   = var.project_id
  
  replication {
    auto {}
  }
  
  labels = {
    app = "chatbot-rag"
  }
}

resource "google_secret_manager_secret_version" "redis_port" {
  secret      = google_secret_manager_secret.redis_port.id
  secret_data = tostring(google_redis_instance.chat_history.port)
}

resource "google_secret_manager_secret" "redis_auth" {
  secret_id = "redis-auth-string"
  project   = var.project_id
  
  replication {
    auto {}
  }
  
  labels = {
    app = "chatbot-rag"
  }
}

resource "google_secret_manager_secret_version" "redis_auth" {
  secret      = google_secret_manager_secret.redis_auth.id
  secret_data = google_redis_instance.chat_history.auth_string
}

# IAM binding for GKE service account to access Redis secrets
resource "google_secret_manager_secret_iam_member" "redis_secrets_accessor" {
  for_each = {
    host = google_secret_manager_secret.redis_host.id
    port = google_secret_manager_secret.redis_port.id
    auth = google_secret_manager_secret.redis_auth.id
  }
  
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gke_sa.email}"
}
