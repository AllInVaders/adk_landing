resource "google_cloud_run_v2_service" "landing_page" {
  name     = "lp-smartbrew-kettle"
  location = "us-central1"
  template {
    containers {
      image = "gcr.io/PROJECT_ID/lp-smartbrew-kettle:latest"
    }
  }
}
