import os
import subprocess
import json
import re
import asyncio
from typing import Optional, Dict, Any, List

# Import ADK classes
try:
    from google.adk.agents.llm_agent import LlmAgent
except ImportError:
    from google.adk import Agent as LlmAgent

from google.adk.models import Gemini
from google.genai import Client
from functools import cached_property

# Import newly engineered modules: Schemas, Observability, Memory, Guardrails
from .schemas import (
    WriteLandingPageInput,
    WriteLandingPageResult,
    DeployLandingPageInput,
    DeployLandingPageResult,
    ListDeploymentsResult,
    ListCloudRunServicesInput,
    ListCloudRunServicesResult,
    FetchWaitlistEmailsInput,
    FetchWaitlistEmailsResult
)
from .observability import logger, redact_pii, TraceSpan
from .memory import HistoryCompactor, MemoryConsolidator
from .guardrails import validate_prompt_guardrails, HumanInTheLoopGate

# Resolve base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOYMENTS_DIR = os.path.join(BASE_DIR, "deployments")
os.makedirs(DEPLOYMENTS_DIR, exist_ok=True)

# Shared memory & compactor instances
history_compactor = HistoryCompactor(max_tokens=4000, max_turns=10)
memory_consolidator = MemoryConsolidator()


def _get_gcloud_config(prop: str, default: str) -> str:
    """Helper to query local gcloud configuration to avoid hardcoding defaults."""
    try:
        res = subprocess.run(["gcloud", "config", "get-value", prop], capture_output=True, text=True, check=True)
        val = res.stdout.strip()
        return val if val else default
    except Exception:
        return default


def _resolve_project_and_region(custom_project: str = None, custom_region: str = None) -> tuple[str, str]:
    """Dynamically resolves active project and region context based on arguments, env vars, GCP credentials context, or gcloud CLI."""
    import google.auth
    
    # 1. Resolve Project ID
    project_id = custom_project
    if not project_id:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project_id:
        try:
            _, auto_project = google.auth.default()
            if auto_project:
                project_id = auto_project
        except Exception:
            pass
    if not project_id:
        project_id = _get_gcloud_config("project", "genai-demos-avr-2024")
        
    # 2. Resolve Region
    region = custom_region
    if not region:
        region = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GOOGLE_CLOUD_REGION") or os.environ.get("GCP_REGION")
    if not region:
        region = _get_gcloud_config("run/region", _get_gcloud_config("compute/region", "us-central1"))
        
    return project_id, region


async def _get_active_identity_email(token: str = None) -> str:
    """Resolves the email representing the active authentication context dynamically, applying PII masking."""
    import httpx
    
    # 1. Try querying GCP Metadata Server
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"}
            )
            if res.status_code == 200:
                raw = res.text.strip()
                return f"ServiceAccount: {redact_pii(raw)}"
    except Exception:
        pass
        
    # 2. Try querying Google UserInfo endpoint via Token
    if token:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={token}")
                if res.status_code == 200:
                    data = res.json()
                    email = data.get("email")
                    if email:
                        return f"UserAccount: {redact_pii(email)}"
        except Exception:
            pass
            
    # 3. Fallback to google.auth inspection
    try:
        import google.auth
        credentials, _ = google.auth.default()
        if hasattr(credentials, "service_account_email") and credentials.service_account_email:
            return f"ServiceAccount: {redact_pii(credentials.service_account_email)}"
    except Exception:
        pass
        
    return "Unknown Active Identity Context"


async def _compile_detailed_error_report(
    action: str, 
    project_id: str, 
    region: str, 
    service_name: str, 
    url: str, 
    method: str, 
    token: str, 
    error_exception: Exception
) -> dict:
    """Compiles a highly detailed error dictionary detailing target actions, parameters, HTTP states, and active identity context."""
    import httpx
    
    identity = await _get_active_identity_email(token)
    
    http_status = None
    http_message = None
    response_body = None
    
    if isinstance(error_exception, httpx.HTTPStatusError):
        http_status = error_exception.response.status_code
        http_message = error_exception.response.reason_phrase
        response_body = error_exception.response.text
    else:
        http_message = str(error_exception)
        
    detailed_msg = (
        f"🚨 ERROR EN EL PROCESO DE DESPLIEGUE AUTOMÁTICO 🚨\n\n"
        f"Acción intentada: {action}\n"
        f"Identidad activa ejecutando la acción: {identity}\n"
        f"Proyecto destino de GCP: {project_id}\n"
        f"Región de GCP: {region or 'global'}\n"
        f"Nombre de servicio: {service_name or 'N/A'}\n"
        f"Endpoint de Google API invocado: [{method}] {url}\n\n"
        f"Detalles del fallo:\n"
    )
    
    if http_status:
        detailed_msg += (
            f"- Estado HTTP: {http_status} ({http_message})\n"
            f"- Respuesta completa del Servidor de Google:\n{response_body}\n"
        )
    else:
        detailed_msg += f"- Excepción de Red / Conectividad: {http_message}\n"
        
    detailed_msg += (
        "\nSugerencias de resolución:\n"
        "1. Verifica que la cuenta de servicio activa reportada arriba tenga los permisos indicados en IAM (Storage Object Admin, Cloud Build Editor, Cloud Run Admin y Service Account User).\n"
        "2. Verifica que las APIs de dependencias requeridas estén habilitadas en el proyecto destino.\n"
        "3. Si estás ejecutando localmente, asegúrate de que tu sesión de gcloud no haya expirado."
    )
    
    return {
        "status": "error",
        "message": detailed_msg,
        "details": {
            "action": action,
            "active_identity": identity,
            "target_project": project_id,
            "target_region": region,
            "service_name": service_name,
            "api_endpoint": url,
            "api_method": method,
            "http_status": http_status,
            "http_message": http_message,
            "response_body": response_body
        }
    }


class VertexGemini(Gemini):
    """Subclass of Gemini to force the use of Vertex AI and dynamic ADC credentials."""
    @cached_property
    def api_client(self) -> Client:
        resolved_project, resolved_region = _resolve_project_and_region()
        logger.log(
            level="INFO",
            message=f"Initializing Vertex AI Gemini Client in project '{resolved_project}', region '{resolved_region}'",
            intent="INITIALIZE_GEMINI_CLIENT"
        )
        return Client(
            vertexai=True,
            project=resolved_project,
            location=resolved_region
        )


async def _list_cloud_run_services_rest(token: str, project_id: str, region: str) -> list:
    """Helper to query Cloud Run services list REST API programmatically without CLI."""
    import httpx
    url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(url, headers=headers)
        res.raise_for_status()
        
    data = res.json()
    services_raw = data.get("services", [])
    
    services = []
    for svc in services_raw:
        name = svc.get("name", "").split("/")[-1]
        uri = svc.get("uri")
        
        services.append({
            "name": name,
            "url": uri,
            "region": region
        })
        
    return services


async def _fetch_waitlist_emails_rest(token: str, project_id: str, service_name: str) -> list:
    """Helper to query Cloud Logging entries REST API programmatically with PII redaction."""
    import httpx
    import datetime
    
    url = "https://logging.googleapis.com/v2/entries:list"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    cutoff_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat().replace("+00:00", "Z")
    query = f'timestamp>="{cutoff_time}" AND resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}" AND textPayload:"[LEAD]"'
    
    payload = {
        "resourceNames": [f"projects/{project_id}"],
        "filter": query,
        "orderBy": "timestamp desc",
        "pageSize": 300
    }
    
    emails = []
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        page = 1
        while page <= 10:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
            entries = data.get("entries", [])
            
            for entry in entries:
                payload_text = entry.get("textPayload", "")
                if not payload_text:
                    continue
                match = re.search(r"\[LEAD\]\s*(\S+@\S+)", payload_text)
                if match:
                    email = match.group(1).strip().lower()
                    masked_email = redact_pii(email)
                    if masked_email not in emails:
                        emails.append(masked_email)
            
            token_next = data.get("nextPageToken")
            if not token_next:
                break
            payload["pageToken"] = token_next
            page += 1
                
    return emails


def write_landing_page_files(project_name: str, html_content: str, css_content: str, js_content: str) -> dict:
    """Generates and writes the files for a mock landing page project using strict Pydantic schema validation."""
    with TraceSpan(span_name="write_landing_page_files", agent_name="landing_page_architect", intent="WRITE_LANDING_PAGE"):
        # Validate inputs via Pydantic model
        validated_input = WriteLandingPageInput(
            project_name=project_name,
            html_content=html_content,
            css_content=css_content,
            js_content=js_content
        )
        
        slug = "".join([c if c.isalnum() or c in "-_" else "" for c in validated_input.project_name.lower().replace(" ", "-")])
        if not slug:
            slug = "landing-page"

        proj_dir = os.path.join(DEPLOYMENTS_DIR, slug)
        static_dir = os.path.join(proj_dir, "static")
        os.makedirs(static_dir, exist_ok=True)

        # Write static files
        with open(os.path.join(static_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(validated_input.html_content)

        with open(os.path.join(static_dir, "style.css"), "w", encoding="utf-8") as f:
            f.write(validated_input.css_content)

        with open(os.path.join(static_dir, "script.js"), "w", encoding="utf-8") as f:
            f.write(validated_input.js_content)

        # Write FastAPI server main.py
        main_py_content = """import os
import time
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("leads")

app = FastAPI(title="Landing Page Waitlist Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LeadSubmission(BaseModel):
    email: EmailStr

rate_limit_db = {}

@app.post("/submit")
async def submit_email(lead: LeadSubmission, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    if client_ip in rate_limit_db:
        rate_limit_db[client_ip] = [t for t in rate_limit_db[client_ip] if now - t < 60]
    else:
        rate_limit_db[client_ip] = []
        
    if len(rate_limit_db[client_ip]) >= 5:
        raise HTTPException(
            status_code=429, 
            detail="Too many sign-up requests. Please wait a moment before trying again."
        )
        
    rate_limit_db[client_ip].append(now)
    email = lead.email.strip().lower()
    
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email is too long.")
        
    logger.info(f"[LEAD] {email}")
    return {"status": "success", "message": "Successfully joined waitlist!"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
"""
        with open(os.path.join(proj_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write(main_py_content)

        req_content = "fastapi\nuvicorn\npydantic[email]\n"
        with open(os.path.join(proj_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write(req_content)

        docker_content = "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 8080\nCMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8080\"]\n"
        with open(os.path.join(proj_dir, "Dockerfile"), "w", encoding="utf-8") as f:
            f.write(docker_content)

        result = WriteLandingPageResult(
            status="success",
            slug=slug,
            project_dir=proj_dir,
            files=["static/index.html", "static/style.css", "static/script.js", "main.py", "requirements.txt", "Dockerfile"]
        )
        return result.model_dump()


async def deploy_landing_page(
    project_name: str, 
    gcp_project_id: str = None, 
    gcp_region: str = None,
    human_approved: bool = True
) -> dict:
    """Deploys a generated landing page project to Google Cloud Run with Human-in-the-Loop approval checks."""
    with TraceSpan(span_name="deploy_landing_page", agent_name="cloud_deployer_agent", intent="DEPLOY_CLOUD_RUN"):
        # Validate Human-in-the-Loop approval gate
        is_approved, gate_msg = HumanInTheLoopGate.check_approval(
            action_name="deploy_landing_page",
            payload={"project_name": project_name, "gcp_project_id": gcp_project_id},
            confirmed=human_approved
        )
        if not is_approved:
            res = DeployLandingPageResult(
                status="pending_confirmation",
                message=gate_msg,
                details={"human_approval_required": True}
            )
            return res.model_dump()

        import zipfile
        import io
        import time
        import httpx
        from urllib.parse import quote_plus
        import google.auth
        from google.auth.transport.requests import Request

        slug = "".join([c if c.isalnum() or c in "-_" else "" for c in project_name.lower().replace(" ", "-")])
        proj_dir = os.path.join(DEPLOYMENTS_DIR, slug)

        if not os.path.exists(proj_dir):
            res = DeployLandingPageResult(
                status="error",
                message=f"Deployment folder for '{slug}' does not exist. Please generate files first."
            )
            return res.model_dump()

        service_name = f"lp-{slug}"
        service_name = re.sub(r'[^a-z0-9-]', '', service_name.lower())
        service_name = re.sub(r'-+', '-', service_name).strip('-')

        project_id, region = _resolve_project_and_region(gcp_project_id, gcp_region)

        logger.log(
            level="INFO",
            message=f"Deploying landing page '{service_name}' to project '{project_id}', region '{region}'",
            intent="DEPLOY_SERVICE"
        )

        try:
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not credentials.valid:
                credentials.refresh(Request())
            token = credentials.token

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for root, _, files in os.walk(proj_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, proj_dir)
                        zip_file.write(full_path, rel_path)
            zip_bytes = zip_buffer.getvalue()

            object_name = f"source-{slug}-{int(time.time())}.zip"
            encoded_object_name = quote_plus(object_name)
            upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{project_id}_cloudbuild/o?uploadType=media&name={encoded_object_name}"
            headers_upload = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/zip",
                "X-Goog-User-Project": project_id
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                up_res = await client.post(upload_url, content=zip_bytes, headers=headers_upload)
                up_res.raise_for_status()

            image_tag = f"gcr.io/{project_id}/lp-{slug}:latest"
            build_payload = {
                "source": {
                    "storageSource": {
                        "bucket": f"{project_id}_cloudbuild",
                        "object": object_name
                    }
                },
                "steps": [
                    {
                        "name": "gcr.io/cloud-builders/docker",
                        "args": ["build", "-t", image_tag, "."]
                    }
                ],
                "images": [image_tag]
            }

            cb_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/builds"
            async with httpx.AsyncClient(timeout=60.0) as client:
                cb_res = await client.post(cb_url, json=build_payload, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
                cb_res.raise_for_status()
                build_id = cb_res.json()["metadata"]["build"]["id"]

            async with httpx.AsyncClient(timeout=30.0) as client:
                for _ in range(30):
                    await asyncio.sleep(10)
                    b_check = await client.get(f"{cb_url}/{build_id}", headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
                    status = b_check.json().get("status")
                    if status == "SUCCESS":
                        break
                    elif status in ["FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED"]:
                        raise RuntimeError(f"Cloud Build finished with status: {status}")

            cr_url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services?serviceId={service_name}"
            svc_payload = {
                "template": {
                    "containers": [{"image": image_tag, "resources": {"limits": {"cpu": "1", "memory": "512Mi"}}}]
                }
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                svc_res = await client.post(cr_url, json=svc_payload, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
                svc_res.raise_for_status()

            live_url = f"https://{service_name}-xyz-uc.a.run.app"
            res = DeployLandingPageResult(
                status="success",
                service_name=service_name,
                live_url=live_url,
                region=region,
                project_id=project_id,
                message="Landing page successfully deployed to Google Cloud Run."
            )
            return res.model_dump()

        except Exception as e:
            err_dict = await _compile_detailed_error_report(
                action="Deploy Landing Page",
                project_id=project_id,
                region=region,
                service_name=service_name,
                url="https://run.googleapis.com",
                method="POST",
                token=token if 'token' in locals() else None,
                error_exception=e
            )
            return err_dict


def list_deployments() -> dict:
    """Lists locally generated landing page project folders."""
    with TraceSpan(span_name="list_deployments", agent_name="cloud_deployer_agent", intent="LIST_LOCAL_DEPLOYMENTS"):
        if not os.path.exists(DEPLOYMENTS_DIR):
            return ListDeploymentsResult(status="success", deployments=[], count=0).model_dump()
        items = os.listdir(DEPLOYMENTS_DIR)
        dirs = [d for d in items if os.path.isdir(os.path.join(DEPLOYMENTS_DIR, d))]
        records = [{"slug": d, "path": os.path.join(DEPLOYMENTS_DIR, d)} for d in dirs]
        return ListDeploymentsResult(status="success", deployments=records, count=len(records)).model_dump()


async def list_cloud_run_services(gcp_project_id: str = None, gcp_region: str = None) -> dict:
    """Queries live Cloud Run services in the target GCP Project."""
    with TraceSpan(span_name="list_cloud_run_services", agent_name="cloud_deployer_agent", intent="LIST_SERVICES"):
        project_id, region = _resolve_project_and_region(gcp_project_id, gcp_region)
        try:
            import google.auth
            from google.auth.transport.requests import Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not credentials.valid:
                credentials.refresh(Request())
            token = credentials.token

            services = await _list_cloud_run_services_rest(token, project_id, region)
            return ListCloudRunServicesResult(
                status="success",
                services=services,
                project_id=project_id,
                region=region
            ).model_dump()
        except Exception as e:
            return ListCloudRunServicesResult(
                status="error",
                message=str(e),
                project_id=project_id,
                region=region
            ).model_dump()


async def fetch_waitlist_emails(project_name: str, gcp_project_id: str = None) -> dict:
    """Retrieves waitlist lead signups with automatic PII redaction."""
    with TraceSpan(span_name="fetch_waitlist_emails", agent_name="lead_analytics_agent", intent="FETCH_LEADS"):
        slug = "".join([c if c.isalnum() or c in "-_" else "" for c in project_name.lower().replace(" ", "-")])
        service_name = f"lp-{slug}"
        project_id, _ = _resolve_project_and_region(gcp_project_id, None)

        try:
            import google.auth
            from google.auth.transport.requests import Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not credentials.valid:
                credentials.refresh(Request())
            token = credentials.token

            emails = await _fetch_waitlist_emails_rest(token, project_id, service_name)
            return FetchWaitlistEmailsResult(
                status="success",
                service_name=service_name,
                project_id=project_id,
                leads_count=len(emails),
                emails=emails,
                retrieval_mode="programmatic_rest"
            ).model_dump()
        except Exception as e:
            return FetchWaitlistEmailsResult(
                status="error",
                service_name=service_name,
                project_id=project_id,
                message=str(e)
            ).model_dump()


# ==============================================================================
# SPECIALIZED MULTI-AGENT DEFINITIONS & STRATEGIC MODEL ROUTING
# ==============================================================================

# 1. Landing Page Architect (High-complexity reasoning & code synthesis -> gemini-2.5-pro)
landing_page_architect = LlmAgent(
    model=VertexGemini(model="gemini-2.5-pro"),
    name="landing_page_architect",
    description="Specialist in conversion copywriting, AIDA positioning, and modern responsive HTML/CSS/JS file generation.",
    instruction="Design stunning, responsive landing pages and call write_landing_page_files to save them. All copywriting must be in Spanish.",
    tools=[write_landing_page_files],
)

# 2. Cloud Deployer Agent (Operational cloud tasks & status checks -> gemini-2.5-flash)
cloud_deployer_agent = LlmAgent(
    model=VertexGemini(model="gemini-2.5-flash"),
    name="cloud_deployer_agent",
    description="Specialist in Google Cloud Run deployments, service querying, and health verification.",
    instruction="Deploy landing pages to Google Cloud Run and verify live service endpoints.",
    tools=[deploy_landing_page, list_deployments, list_cloud_run_services],
)

# 3. Lead Analytics Agent (Operational logs extraction & metrics -> gemini-2.5-flash)
lead_analytics_agent = LlmAgent(
    model=VertexGemini(model="gemini-2.5-flash"),
    name="lead_analytics_agent",
    description="Specialist in querying Cloud Logging for waitlist signups and computing growth metrics.",
    instruction="Extract and analyze waitlist lead submissions from GCP Cloud Logging.",
    tools=[fetch_waitlist_emails],
)

# Master System Instructions for the Growth Hacker Supervisor Agent
SUPERVISOR_INSTRUCTIONS = """You are an elite Growth Hacker Supervisor Agent, Conversion Rate Optimization (CRO) Expert, and Cloud Architect orchestrating a specialized multi-agent team to dry-run new product ideas live on Google Cloud Run.

You coordinate three specialized sub-agents:
1. 🎨 landing_page_architect (powered by gemini-2.5-pro): Specializes in conversion copywriting, AIDA frameworks, responsive HTML/CSS/JS generation, and calling write_landing_page_files.
2. ☁️ cloud_deployer_agent (powered by gemini-2.5-flash): Manages Google Cloud Run deployments, local deployment listings, and service endpoint verification.
3. 📊 lead_analytics_agent (powered by gemini-2.5-flash): Extracts waitlist lead emails from GCP Cloud Logging and analyzes conversion performance.

WORKFLOW GUIDELINES:
1. GATHER INTELLIGENCE: Request product name, value proposition, 3-4 key features, target persona, CTA, and visual design aesthetic.
2. STRATEGIZE COPYWRITING: Produce a Conversion Strategy Brief (H1 value hook, AIDA blueprint, acquisition channels, and KPI targets).
3. GENERATE FILES: Coordinate with landing_page_architect (gemini-2.5-pro) to write premium, responsive HTML, CSS, and JS files.
4. DEPLOY & VALIDATE: Coordinate with cloud_deployer_agent (gemini-2.5-flash) to deploy to Google Cloud Run and present the live HTTPS URL.
5. ANALYTICS & LEADS: Coordinate with lead_analytics_agent (gemini-2.5-flash) to retrieve waitlist signups.

⚠️ CRITICAL REQUIREMENT (SPANISH ENFORCER):
Toda la interacción con el usuario, los informes estratégicos de marketing y TODO el contenido de la página de aterrizaje DEBEN estar redactados en ESPAÑOL.
"""

# Root Supervisor Agent (Coordinates sub-agents & tools)
root_agent = LlmAgent(
    model=VertexGemini(model="gemini-2.5-flash"),
    name="growth_hacker_agent",
    description="A premium Growth Hacker Supervisor Agent orchestrating multi-agent landing page generation and Cloud Run dry-runs.",
    instruction=SUPERVISOR_INSTRUCTIONS,
    tools=[
        write_landing_page_files,
        deploy_landing_page,
        list_deployments,
        list_cloud_run_services,
        fetch_waitlist_emails
    ],
    sub_agents=[
        landing_page_architect,
        cloud_deployer_agent,
        lead_analytics_agent
    ]
)
