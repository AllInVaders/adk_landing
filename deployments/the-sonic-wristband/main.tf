resource "google_cloud_run_v2_service" "landing_page" {
  name     = "lp-the-sonic-wristband"
  location = "us-central1"
  template {
    containers {
      image = "gcr.io/PROJECT_ID/lp-the-sonic-wristband:latest"
    }
  }
}
