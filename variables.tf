variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID where resources will be provisioned."
  default     = "genai-demos-avr-2024"
}

variable "region" {
  type        = string
  description = "The GCP Region for Cloud Run deployment."
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  description = "The base name for the Cloud Run landing page service."
  default     = "lp-growth-hacker"
}

variable "container_image" {
  type        = string
  description = "Container image URI for Cloud Run service."
  default     = "gcr.io/genai-demos-avr-2024/lp-growth-hacker:latest"
}
