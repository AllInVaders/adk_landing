"""Pydantic v2 validation models and JSON schemas for Growth Hacker Agent tools.

Defines strict input and output contracts for all tool invocations, ensuring
type safety, schema verification, and deterministic error responses.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, EmailStr, field_validator


class WriteLandingPageInput(BaseModel):
    """Strict input schema for generating and saving landing page files."""
    project_name: str = Field(
        ...,
        description="Name or slug of the project (e.g. 'smartbrew-kettle' or 'sonic-wristband').",
        min_length=2,
        max_length=64
    )
    html_content: str = Field(
        ...,
        description="Complete HTML5 index.html markup.",
        min_length=20
    )
    css_content: str = Field(
        ...,
        description="Complete style.css stylesheet.",
        min_length=10
    )
    js_content: str = Field(
        ...,
        description="Complete script.js client-side script.",
        min_length=10
    )

    @field_validator("project_name")
    @classmethod
    def sanitize_project_name(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("project_name cannot be empty or whitespace.")
        return cleaned


class WriteLandingPageResult(BaseModel):
    """Strict output schema for landing page file generation."""
    status: Literal["success", "error"] = Field(..., description="Execution status.")
    slug: str = Field(..., description="Sanitized project slug.")
    project_dir: str = Field(..., description="Absolute filesystem path to the project directory.")
    files: List[str] = Field(default_factory=list, description="List of generated relative file paths.")
    error_message: Optional[str] = Field(default=None, description="Detailed error description if status is 'error'.")


class DeployLandingPageInput(BaseModel):
    """Strict input schema for deploying landing page to Google Cloud Run."""
    project_name: str = Field(..., description="Name or slug of the project to deploy.")
    gcp_project_id: Optional[str] = Field(default=None, description="Target GCP project ID.")
    gcp_region: Optional[str] = Field(default=None, description="Target GCP region (e.g., 'us-central1').")
    human_approved: bool = Field(
        default=True,
        description="Human-in-the-Loop approval confirmation flag for cloud deployments."
    )


class DeployLandingPageResult(BaseModel):
    """Strict output schema for Cloud Run deployment."""
    status: Literal["success", "error", "pending_confirmation"] = Field(..., description="Deployment outcome status.")
    service_name: Optional[str] = Field(default=None, description="Cloud Run service name.")
    live_url: Optional[str] = Field(default=None, description="Verified live HTTPS URL of the deployed Cloud Run service.")
    region: Optional[str] = Field(default=None, description="GCP deployment region.")
    project_id: Optional[str] = Field(default=None, description="GCP project ID.")
    message: Optional[str] = Field(default=None, description="Human-readable status or error summary.")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic and debugging metadata.")


class ListDeploymentsResult(BaseModel):
    """Strict output schema for listing local deployments."""
    status: Literal["success", "error"] = Field(..., description="Status of local deployment discovery.")
    deployments: List[Dict[str, Any]] = Field(default_factory=list, description="List of local deployment records.")
    count: int = Field(default=0, description="Total count of discovered local deployments.")


class ListCloudRunServicesInput(BaseModel):
    """Strict input schema for querying live Cloud Run services."""
    gcp_project_id: Optional[str] = Field(default=None, description="GCP Project ID.")
    gcp_region: Optional[str] = Field(default=None, description="GCP Region.")


class ListCloudRunServicesResult(BaseModel):
    """Strict output schema for Cloud Run service queries."""
    status: Literal["success", "error"] = Field(..., description="Query status.")
    services: List[Dict[str, Any]] = Field(default_factory=list, description="Discovered Cloud Run services.")
    project_id: Optional[str] = Field(default=None, description="Resolved GCP Project ID.")
    region: Optional[str] = Field(default=None, description="Resolved GCP Region.")
    message: Optional[str] = Field(default=None, description="Error message if query failed.")


class FetchWaitlistEmailsInput(BaseModel):
    """Strict input schema for querying waitlist lead submissions."""
    project_name: str = Field(..., description="Project name or slug.")
    gcp_project_id: Optional[str] = Field(default=None, description="GCP project ID.")


class FetchWaitlistEmailsResult(BaseModel):
    """Strict output schema for waitlist lead extraction."""
    status: Literal["success", "error"] = Field(..., description="Query status.")
    service_name: Optional[str] = Field(default=None, description="Target Cloud Run service name.")
    project_id: Optional[str] = Field(default=None, description="Target GCP project ID.")
    leads_count: int = Field(default=0, description="Total number of captured email leads.")
    emails: List[str] = Field(default_factory=list, description="Redacted list of waitlist lead emails.")
    retrieval_mode: Optional[str] = Field(default=None, description="Source log retrieval mechanism.")
    message: Optional[str] = Field(default=None, description="Error explanation if status is 'error'.")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic details.")
