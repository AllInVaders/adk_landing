output "cloud_run_url" {
  description = "The live public HTTPS endpoint of the deployed Cloud Run landing page."
  value       = google_cloud_run_v2_service.landing_page_service.uri
}

output "service_account_email" {
  description = "Service account email attached to the growth hacker deployment worker."
  value       = google_service_account.agent_sa.email
}
