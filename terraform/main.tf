terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Google Cloud Run Service (Declarative Serverless Deployment)
resource "google_cloud_run_v2_service" "landing_page_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.container_image
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      ports {
        container_port = 8080
      }
    }
  }
}

# 2. Allow unauthenticated public invocations for public landing pages
resource "google_cloud_run_service_iam_binding" "public_access" {
  location = google_cloud_run_v2_service.landing_page_service.location
  project  = google_cloud_run_v2_service.landing_page_service.project
  service  = google_cloud_run_v2_service.landing_page_service.name
  role     = "roles/run.invoker"
  members = [
    "allUsers"
  ]
}

# 3. Dedicated Service Account for the Agent Worker
resource "google_service_account" "agent_sa" {
  account_id   = "growth-hacker-sa"
  display_name = "Growth Hacker Agent Service Account"
}
