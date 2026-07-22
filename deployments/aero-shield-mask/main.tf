resource "google_cloud_run_v2_service" "landing_page" {
  name     = "lp-aero-shield-mask"
  location = "us-central1"
  template {
    containers {
      image = "gcr.io/PROJECT_ID/lp-aero-shield-mask:latest"
    }
  }
}
