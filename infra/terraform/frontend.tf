# Frontend Deployment Infrastructure
# Deploys Angular frontend to Cloud Storage + Cloud CDN for global low-latency access

# Cloud Storage bucket for frontend static files
resource "google_storage_bucket" "frontend" {
  name          = "${var.project_id}-frontend-${var.environment}"
  location      = var.region
  project       = var.project_id
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"  # SPA routing
  }
  
  cors {
    origin          = ["*"]  # Restrict in production
    method          = ["GET", "HEAD", "OPTIONS"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
  
  labels = {
    environment = var.environment
    app         = "chatbot-rag"
    component   = "frontend"
    managed_by  = "terraform"
  }
}

# Make bucket public for website hosting
resource "google_storage_bucket_iam_member" "frontend_public" {
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Cloud CDN backend bucket
resource "google_compute_backend_bucket" "frontend" {
  name        = "${var.project_name}-frontend-backend-${var.environment}"
  project     = var.project_id
  bucket_name = google_storage_bucket.frontend.name
  enable_cdn  = true
  
  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    default_ttl       = 3600      # 1 hour
    max_ttl           = 86400     # 24 hours
    client_ttl        = 3600      # 1 hour
    negative_caching  = true
    
    cache_key_policy {
      include_host           = true
      include_protocol       = true
      include_query_string   = false
    }
  }
}

# Reserve static IP for Load Balancer
resource "google_compute_global_address" "frontend" {
  name         = "${var.project_name}-frontend-ip-${var.environment}"
  project      = var.project_id
  address_type = "EXTERNAL"
  
  labels = {
    app = "chatbot-rag"
  }
}

# URL map for Load Balancer
resource "google_compute_url_map" "frontend" {
  name            = "${var.project_name}-frontend-lb-${var.environment}"
  project         = var.project_id
  default_service = google_compute_backend_bucket.frontend.id
}

# HTTP(S) target proxy
resource "google_compute_target_https_proxy" "frontend" {
  name             = "${var.project_name}-frontend-https-${var.environment}"
  project          = var.project_id
  url_map          = google_compute_url_map.frontend.id
  ssl_certificates = [google_compute_managed_ssl_certificate.frontend.id]
}

# Managed SSL certificate
resource "google_compute_managed_ssl_certificate" "frontend" {
  name    = "${var.project_name}-frontend-cert-${var.environment}"
  project = var.project_id
  
  managed {
    domains = var.frontend_domains
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# Global forwarding rule (HTTPS)
resource "google_compute_global_forwarding_rule" "frontend_https" {
  name                  = "${var.project_name}-frontend-https-${var.environment}"
  project               = var.project_id
  target                = google_compute_target_https_proxy.frontend.id
  port_range            = "443"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL"
  ip_address            = google_compute_global_address.frontend.address
}

# HTTP to HTTPS redirect
resource "google_compute_url_map" "frontend_http_redirect" {
  name    = "${var.project_name}-frontend-http-redirect-${var.environment}"
  project = var.project_id
  
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "frontend_http" {
  name    = "${var.project_name}-frontend-http-${var.environment}"
  project = var.project_id
  url_map = google_compute_url_map.frontend_http_redirect.id
}

resource "google_compute_global_forwarding_rule" "frontend_http" {
  name                  = "${var.project_name}-frontend-http-${var.environment}"
  project               = var.project_id
  target                = google_compute_target_http_proxy.frontend_http.id
  port_range            = "80"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL"
  ip_address            = google_compute_global_address.frontend.address
}

# Variables
variable "frontend_domains" {
  description = "Domain names for the frontend (for SSL cert)"
  type        = list(string)
  default     = ["chatbot.example.com"]
}

# Outputs
output "frontend_bucket_name" {
  description = "Frontend storage bucket name"
  value       = google_storage_bucket.frontend.name
}

output "frontend_url" {
  description = "Frontend URL"
  value       = "https://${google_compute_global_address.frontend.address}"
}

output "frontend_ip_address" {
  description = "Frontend static IP address"
  value       = google_compute_global_address.frontend.address
}

output "frontend_domain_instructions" {
  description = "Instructions for DNS configuration"
  value       = <<-EOT
    Configure your DNS to point to the frontend IP:
    
    A Record:
    Name: @ (or subdomain)
    Type: A
    Value: ${google_compute_global_address.frontend.address}
    
    Or CNAME to:
    ${google_compute_global_address.frontend.address}
  EOT
}
