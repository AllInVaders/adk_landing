resource "google_cloud_run_v2_service" "landing_page" {
  name     = "lp-coffee-pod-recycler"
  location = "us-central1"
  template {
    containers {
      image = "gcr.io/PROJECT_ID/lp-coffee-pod-recycler:latest"
    }
  }
}
