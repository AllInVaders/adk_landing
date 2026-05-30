import os
import subprocess
import json
import re
import asyncio

# Import ADK classes
try:
    from google.adk.agents.llm_agent import LlmAgent
except ImportError:
    from google.adk import Agent as LlmAgent

from google.adk.models import Gemini
from google.genai import Client
from functools import cached_property

# Resolve base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOYMENTS_DIR = os.path.join(BASE_DIR, "deployments")
os.makedirs(DEPLOYMENTS_DIR, exist_ok=True)


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
    import os
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
    """Resolves the email representing the active authentication context dynamically."""
    import httpx
    
    # 1. Try querying GCP Metadata Server (Standard for Compute/Run/Vertex sandboxes)
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"}
            )
            if res.status_code == 200:
                return f"ServiceAccount: {res.text.strip()}"
    except Exception:
        pass
        
    # 2. Try querying Google UserInfo endpoint via Token (Standard for local ADC credentials / user OAuth tokens)
    if token:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={token}")
                if res.status_code == 200:
                    data = res.json()
                    email = data.get("email")
                    if email:
                        return f"UserAccount: {email}"
        except Exception:
            pass
            
    # 3. Fallback to google.auth inspection
    try:
        import google.auth
        credentials, _ = google.auth.default()
        if hasattr(credentials, "service_account_email") and credentials.service_account_email:
            return f"ServiceAccount: {credentials.service_account_email}"
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
    
    # 1. Resolve active identity email dynamically
    identity = await _get_active_identity_email(token)
    
    # 2. Extract HTTP Status and Body if available
    http_status = None
    http_message = None
    response_body = None
    
    if isinstance(error_exception, httpx.HTTPStatusError):
        http_status = error_exception.response.status_code
        http_message = error_exception.response.reason_phrase
        response_body = error_exception.response.text
    else:
        http_message = str(error_exception)
        
    # 3. Construct the strategic Spanish message explaining in detail what was attempted, what failed, and under which identity
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
        print(f"[VertexGemini] Initializing Client in project '{resolved_project}', region '{resolved_region}' using Google Application Default Credentials...")
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
    """Helper to query Cloud Logging entries REST API programmatically without CLI using pagination, 30-day cutoff, and descending sorting."""
    import httpx
    import re
    import datetime
    
    url = "https://logging.googleapis.com/v2/entries:list"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    # Calculate 30-day cutoff to restrict logs query scope and optimize GQL search scan speed
    cutoff_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat().replace("+00:00", "Z")
    
    query = f'timestamp>="{cutoff_time}" AND resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}" AND textPayload:"[LEAD]"'
    
    payload = {
        "resourceNames": [
            f"projects/{project_id}"
        ],
        "filter": query,
        "orderBy": "timestamp desc",
        "pageSize": 300
    }
    
    emails = []
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        page = 1
        # Scan up to 10 pages maximum as a safe boundary
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
                    if email not in emails:
                        emails.append(email)
            
            token_next = data.get("nextPageToken")
            if not token_next:
                break
            payload["pageToken"] = token_next
            page += 1
                
    return emails


def write_landing_page_files(project_name: str, html_content: str, css_content: str, js_content: str) -> dict:
    """Generates and writes the files for a mock landing page project.

    Args:
        project_name: Name of the project (slug, e.g. 'smartbrew' or
          'fitness-tracker').
        html_content: The full HTML5 index.html markup.
        css_content: The full style.css stylesheet.
        js_content: The full script.js client-side script.

    Returns:
        A dictionary containing the status and the paths of the written files.
    """
    # Sanitize project name to a slug
    slug = "".join([c if c.isalnum() or c in "-_" else "" for c in project_name.lower().replace(" ", "-")])
    if not slug:
        slug = "landing-page"

    proj_dir = os.path.join(DEPLOYMENTS_DIR, slug)
    static_dir = os.path.join(proj_dir, "static")
    os.makedirs(static_dir, exist_ok=True)

    # Write static files
    with open(os.path.join(static_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    with open(os.path.join(static_dir, "style.css"), "w", encoding="utf-8") as f:
        f.write(css_content)

    with open(os.path.join(static_dir, "script.js"), "w", encoding="utf-8") as f:
        f.write(js_content)

    # Write FastAPI server main.py
    main_py_content = """import os
import time
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

# Setup clean logger to log waitlist leads to stdout for simple retrieval
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

# In-memory rate limiting database: client_ip -> [timestamps]
rate_limit_db = {}

@app.post("/submit")
async def submit_email(lead: LeadSubmission, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Prune submissions older than 60 seconds
    if client_ip in rate_limit_db:
        rate_limit_db[client_ip] = [t for t in rate_limit_db[client_ip] if now - t < 60]
    else:
        rate_limit_db[client_ip] = []
        
    # Rate limit: Max 5 waitlist submissions per minute from same client IP to protect server
    if len(rate_limit_db[client_ip]) >= 5:
        raise HTTPException(
            status_code=429, 
            detail="Too many sign-up requests. Please wait a moment before trying again."
        )
        
    rate_limit_db[client_ip].append(now)
    
    email = lead.email.strip().lower()
    
    # Safe validation length check
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email is too long.")
        
    # Log directly to stdout so gcloud logging read can retrieve it!
    logger.info(f"[LEAD] {email}")
    
    # Also save to local JSON file inside container as ephemeral backup
    try:
        import json
        emails = []
        if os.path.exists("emails.json"):
            with open("emails.json", "r") as f:
                emails = json.load(f)
        if email not in emails:
            emails.append(email)
            with open("emails.json", "w") as f:
                json.dump(emails, f)
    except Exception:
        pass
        
    return {"status": "success", "message": "Successfully joined waitlist!"}

# Serve the static landing page assets
app.mount("/", StaticFiles(directory="static", html=True), name="static")
"""

    with open(os.path.join(proj_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write(main_py_content)

    # Write requirements.txt
    req_content = """fastapi
uvicorn
pydantic[email]
"""
    with open(os.path.join(proj_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write(req_content)

    # Write Dockerfile
    docker_content = """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
"""
    with open(os.path.join(proj_dir, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write(docker_content)

    return {
        "status": "success",
        "slug": slug,
        "project_dir": proj_dir,
        "files": ["static/index.html", "static/style.css", "static/script.js", "main.py", "requirements.txt", "Dockerfile"]
    }


async def deploy_landing_page(project_name: str, gcp_project_id: str = None, gcp_region: str = None) -> dict:
    """Deploys a generated landing page project to Google Cloud Run.

    It dynamically uses a programmatic Google Cloud REST API client pipeline
    (no local 'gcloud' CLI or local 'docker' required) making it compatible
    both locally and hosted on the Vertex AI cloud agent engine platform.
    If credentials resolution fails, it gracefully falls back to using the
    traditional gcloud CLI subprocess command!

    Args:
        project_name: The name or slug of the project to deploy.
        gcp_project_id: The Google Cloud project ID (autodetected if None).
        gcp_region: The GCP region to deploy to (autodetected if None).

    Returns:
        A dictionary containing the deployment status and verified live URL.
    """
    import zipfile
    import io
    import time
    import httpx
    from urllib.parse import quote_plus, urlparse
    import google.auth
    from google.auth.transport.requests import Request

    slug = "".join([c if c.isalnum() or c in "-_" else "" for c in project_name.lower().replace(" ", "-")])
    proj_dir = os.path.join(DEPLOYMENTS_DIR, slug)

    if not os.path.exists(proj_dir):
        return {"status": "error", "message": f"Deployment folder for '{slug}' does not exist. Please generate files first."}

    # Format service name for Cloud Run
    service_name = f"lp-{slug}"
    service_name = re.sub(r'[^a-z0-9-]', '', service_name.lower())
    service_name = re.sub(r'-+', '-', service_name).strip('-')

    # Resolve dynamic configs for defaults using robust context discovery
    project_id, region = _resolve_project_and_region(gcp_project_id, gcp_region)

    print(f"[Deploy] Initializing programmatic REST deployment for '{service_name}' in project '{project_id}'...")

    # 1. Attempt the REST API deployment pipeline
    try:
        # Resolve OAuth credentials with Cloud Platform scopes for GCS and Cloud Build authorization
        credentials, auto_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid:
            credentials.refresh(Request())
        token = credentials.token
        
        # Phase 1: Compile files in memory to ZIP bytes
        print(f"[Deploy] Phase 1: Archiving local project directory into zip bytes...")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(proj_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, proj_dir)
                    zip_file.write(file_path, rel_path)
        zip_bytes = zip_buffer.getvalue()
        
        # Phase 2: Upload Source ZIP to GCS (Probing pre-existing default staging buckets)
        blob_name = f"sources/{slug}-{int(time.time())}.zip"
        
        # Standard dynamic pre-existing staging buckets in Google Cloud project
        candidate_buckets = [
            f"run-sources-{project_id}-{region}",
            f"{project_id}-adk-staging",
            f"{project_id}_cloudbuild",
            f"gcf-v2-sources-100140771040-{region}", # Numerical staging fallback
            "genai-demos-avr-2024-bucket"
        ]
        
        bucket_name = None
        
        print(f"[Deploy] Phase 2: Uploading source zip ({len(zip_bytes)} bytes) to a writable staging GCS bucket...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            for candidate in candidate_buckets:
                print(f"[Deploy] Probing candidate staging bucket: '{candidate}'...")
                upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{candidate}/o?uploadType=media&name={quote_plus(blob_name)}"
                headers = {
                    "Authorization": f"Bearer {token}", 
                    "Content-Type": "application/zip",
                    "X-Goog-User-Project": project_id
                }
                
                try:
                    upload_res = await client.post(upload_url, content=zip_bytes, headers=headers)
                    if upload_res.status_code == 200:
                        bucket_name = candidate
                        print(f"✅ [Deploy] Staging completed! Source uploaded successfully to pre-existing bucket: '{bucket_name}'!")
                        break
                    else:
                        print(f"  [Probe] Candidate bucket '{candidate}' upload failed with status: {upload_res.status_code}")
                except Exception as e:
                    print(f"  [Probe] Candidate bucket '{candidate}' connection failed: {e}")
                    
            if not bucket_name:
                # Try to create the run-sources bucket!
                target_bucket = f"run-sources-{project_id}-{region}"
                print(f"[Deploy] None of the pre-existing staging buckets were writable. Attempting to dynamically create standard Cloud Run staging bucket: '{target_bucket}'...")
                create_url = f"https://storage.googleapis.com/storage/v1/b?project={project_id}"
                create_payload = {
                    "name": target_bucket,
                    "location": region
                }
                create_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Goog-User-Project": project_id
                }
                
                try:
                    create_res = await client.post(create_url, json=create_payload, headers=create_headers)
                    if create_res.status_code not in (200, 409):
                        create_res.raise_for_status()
                        
                    print(f"✅ [Deploy] Staging bucket status resolved ({create_res.status_code}). Retrying source upload to '{target_bucket}'...")
                    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{target_bucket}/o?uploadType=media&name={quote_plus(blob_name)}"
                    upload_headers = {
                        "Authorization": f"Bearer {token}", 
                        "Content-Type": "application/zip",
                        "X-Goog-User-Project": project_id
                    }
                    upload_res = await client.post(upload_url, content=zip_bytes, headers=upload_headers)
                    upload_res.raise_for_status()
                    
                    bucket_name = target_bucket
                    print(f"✅ [Deploy] Staging completed! Source uploaded successfully to newly resolved staging bucket: '{bucket_name}'!")
                except Exception as create_err:
                    print(f"⚠️ [Deploy] Bucket staging resolution / retry upload failed: {create_err}")
                    raise create_err
                    
            if not bucket_name:
                raise Exception("Failed to stage source zip. Dynamic staging resolution was unsuccessful.")
                
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        
        # Phase 3: Trigger Cloud Build Run
        image_uri = f"{region}-docker.pkg.dev/genai-demos-avr-2024/lp-images/lp-{slug}:latest"
        build_payload = {
            "source": {
                "storageSource": {
                    "bucket": bucket_name,
                    "object": blob_name
                }
            },
            "steps": [
                {
                    "name": "gcr.io/cloud-builders/docker",
                    "args": ["build", "-t", image_uri, "."]
                },
                {
                    "name": "gcr.io/cloud-builders/gcloud",
                    "entrypoint": "bash",
                    "args": ["-c", "gcloud auth print-access-token > /workspace/token.txt"]
                },
                {
                    "name": "gcr.io/cloud-builders/docker",
                    "entrypoint": "bash",
                    "args": [
                        "-c",
                        f"cat /workspace/token.txt | docker login -u oauth2accesstoken --password-stdin https://{region}-docker.pkg.dev"
                    ]
                },
                {
                    "name": "gcr.io/cloud-builders/docker",
                    "args": ["push", image_uri]
                }
            ],
            "serviceAccount": "projects/genai-demos-avr-2024/serviceAccounts/100140771040-compute@developer.gserviceaccount.com",
            "logsBucket": f"gs://{bucket_name}"
        }
        
        print(f"[Deploy] Phase 3: Triggering Cloud Build (Image destination: {image_uri})...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            trigger_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/global/builds"
            build_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": project_id
            }
            build_res = await client.post(trigger_url, json=build_payload, headers=build_headers)
            build_res.raise_for_status()
            
            op_data = build_res.json()
            op_name = op_data.get("name")
            print(f"[Deploy] Cloud Build triggered! Operation reference: {op_name}. Polling status...")
            
            # Cloud Build Polling Loop
            poll_url = f"https://cloudbuild.googleapis.com/v1/{op_name}"
            max_build_retries = 30  # 30 * 10s = 5 minutes wait
            
            for build_check in range(1, max_build_retries + 1):
                await asyncio.sleep(10)
                status_headers = {
                    "Authorization": f"Bearer {token}",
                    "X-Goog-User-Project": project_id
                }
                status_res = await client.get(poll_url, headers=status_headers)
                status_res.raise_for_status()
                status_data = status_res.json()
                
                metadata = status_data.get("metadata", {})
                build_status = metadata.get("build", {}).get("status")
                print(f"  [Build Status Check #{build_check}]: {build_status}")
                
                if status_data.get("done", False):
                    final_status = metadata.get("build", {}).get("status")
                    if final_status != "SUCCESS":
                        raise Exception(f"Cloud Build finished with failure status: {final_status}")
                    print("✅ [Deploy] Cloud Build compiled and pushed container image successfully!")
                    break
            else:
                raise TimeoutError("Cloud Build compilation timed out.")
                
        # Phase 4: Deploy Container Revision to Cloud Run
        service_payload = {
            "template": {
                "containers": [
                    {
                        "image": image_uri
                    }
                ]
            }
        }
        
        base_run_url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services"
        service_url = f"{base_run_url}/{service_name}"
        
        print(f"[Deploy] Phase 4: Triggering Cloud Run deployment for service '{service_name}'...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            run_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": project_id
            }
            # Verify if service already exists
            exists = False
            try:
                get_res = await client.get(service_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
                if get_res.status_code == 200:
                    exists = True
            except Exception:
                pass
                
            if not exists:
                print(f"[Deploy] Service '{service_name}' does not exist. Creating new service...")
                create_url = f"{base_run_url}?serviceId={service_name}"
                res = await client.post(create_url, json=service_payload, headers=run_headers)
                res.raise_for_status()
            else:
                print(f"[Deploy] Service '{service_name}' exists. Patching container revision template...")
                patch_url = f"{service_url}?updateMask=template.containers"
                res = await client.patch(patch_url, json=service_payload, headers=run_headers)
                res.raise_for_status()
                
            # Phase 5: Verification and Public IAM Policy Update Loop
            print(f"[Deploy] Entering Cloud Run verification loop. Checking every 20 seconds...")
            max_run_retries = 15  # 15 * 20s = 5 minutes wait
            live_url = None
            
            for run_check in range(1, max_run_retries + 1):
                await asyncio.sleep(20)
                status_res = await client.get(service_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
                status_res.raise_for_status()
                status_data = status_res.json()
                
                uri = status_data.get("uri")
                if uri and uri.startswith("https://"):
                    live_url = uri
                    print(f"✅ Verified! Cloud Run service active at: {live_url}")
                    
                    # Make service public (allow-unauthenticated) by granting run.invoker role to allUsers
                    print(f"[Deploy] Modifying IAM Policy to grant public allow-unauthenticated invoker access...")
                    iam_url = f"{service_url}:setIamPolicy"
                    iam_payload = {
                        "policy": {
                            "bindings": [
                                {
                                    "role": "roles/run.invoker",
                                    "members": ["allUsers"]
                                }
                            ]
                        }
                    }
                    try:
                        iam_res = await client.post(iam_url, json=iam_payload, headers=run_headers)
                        iam_res.raise_for_status()
                        print(f"✅ Verified! Public IAM Invoker policy applied successfully.")
                        iam_success = True
                    except Exception as iam_err:
                        print(f"⚠️ [Deploy] Could not grant public (allow-unauthenticated) invoker role to allUsers: {iam_err}")
                        print(f"⚠️ [Deploy] The service might require authentication when called.")
                        iam_success = False
                    break
            else:
                raise TimeoutError("Cloud Run live URL resolution timed out.")
                
            return {
                "status": "success",
                "service_name": service_name,
                "project_id": project_id,
                "region": region,
                "live_url": live_url,
                "deployment_mode": "programmatic_rest",
                "verification_attempts": run_check,
                "public_access": iam_success
            }
            
    except Exception as rest_error:
        # Determine the action phase that triggered the error
        action_phase = "Deployment Orchestrator"
        target_url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services"
        target_method = "GET"
        
        # Parse trace stack variables to report the exact failing phase in detail
        import traceback
        tb = traceback.format_exc()
        if "_fetch_waitlist_emails_rest" in tb or "logging" in tb:
            action_phase = "Querying Lead Logs (fetch_waitlist)"
            target_url = "https://logging.googleapis.com/v2/entries:list"
            target_method = "POST"
        elif "cloudbuild" in tb:
            action_phase = "Triggering Docker Image Compile (Cloud Build)"
            target_url = f"https://cloudbuild.googleapis.com/v1/projects/{project_id}/locations/global/builds"
            target_method = "POST"
        elif "storage" in tb or "upload" in tb:
            action_phase = "Uploading Source Code (Staging) to GCS Bucket"
            target_url = f"https://storage.googleapis.com/storage/v1/b?project={project_id}"
            target_method = "POST"
        elif "setIamPolicy" in tb:
            action_phase = "Granting public allow-unauthenticated invoker access (IAM setIamPolicy)"
            target_url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services/{service_name}:setIamPolicy"
            target_method = "POST"
        elif "create_url" in tb or "patch_url" in tb:
            action_phase = "Deploying Container Revision (Cloud Run API)"
            target_url = f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services/{service_name}"
            target_method = "POST" if "create_url" in tb else "PATCH"
            
        print(f"⚠️ [Deploy] Programmatic REST deployment pipeline failed inside phase: '{action_phase}'!")
        
        return await _compile_detailed_error_report(
            action=action_phase,
            project_id=project_id,
            region=region,
            service_name=service_name,
            url=target_url,
            method=target_method,
            token=token if 'token' in locals() else None,
            error_exception=rest_error
        )


def list_deployments() -> dict:
    """Lists all landing page projects generated under the deployments directory.

    Returns:
        A dictionary containing the list of deployments.
    """
    if not os.path.exists(DEPLOYMENTS_DIR):
        return {"status": "success", "deployments": []}

    projects = []
    for item in os.listdir(DEPLOYMENTS_DIR):
        path = os.path.join(DEPLOYMENTS_DIR, item)
        if os.path.isdir(path):
            has_html = os.path.exists(os.path.join(path, "static", "index.html"))
            projects.append({
                "slug": item,
                "has_html": has_html,
                "project_dir": path
            })

    return {"status": "success", "deployments": projects}


async def list_cloud_run_services(gcp_project_id: str = None, gcp_region: str = None) -> dict:
    """Lists all active Google Cloud Run services and their live URLs.

    Args:
        gcp_project_id: The Google Cloud project ID (autodetected if None).
        gcp_region: The GCP region to list services from (autodetected if None).

    Returns:
        A dictionary containing the status and the list of services with their URLs.
    """
    import httpx
    import google.auth
    from google.auth.transport.requests import Request
    
    # Resolve dynamic configs for defaults using robust context discovery
    project_id, region = _resolve_project_and_region(gcp_project_id, gcp_region)
    
    # 1. Try programmatic REST API (Compatible in CLI-free hosted platforms)
    try:
        credentials, auto_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid:
            credentials.refresh(Request())
        token = credentials.token
        
        print(f"[List] Querying Cloud Run services via REST API in project '{project_id}' (Region: '{region}')...")
        services = await _list_cloud_run_services_rest(token, project_id, region)
        
        return {
            "status": "success",
            "project_id": project_id,
            "region": region,
            "services_count": len(services),
            "services": services,
            "retrieval_mode": "programmatic_rest"
        }
        
    except Exception as rest_err:
        print(f"⚠️ [List] Programmatic REST service listing failed!")
        
        identity = await _get_active_identity_email(token if 'token' in locals() else None)
        
        import httpx
        http_status = None
        http_message = None
        response_body = None
        
        if isinstance(rest_err, httpx.HTTPStatusError):
            http_status = rest_err.response.status_code
            http_message = rest_err.response.reason_phrase
            response_body = rest_err.response.text
        else:
            http_message = str(rest_err)
            
        detailed_msg = (
            f"🚨 ERROR AL ENLISTAR SERVICIOS DE CLOUD RUN 🚨\n\n"
            f"Acción intentada: Enlistar servicios activos (List Services)\n"
            f"Identidad activa ejecutando la acción: {identity}\n"
            f"Proyecto destino de GCP: {project_id}\n"
            f"Región de GCP: {region}\n"
            f"Endpoint de Google API invocado: [GET] https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services\n\n"
            f"Detalles del fallo:\n"
        )
        
        if http_status:
            detailed_msg += (
                f"- Estado HTTP: {http_status} ({http_message})\n"
                f"- Respuesta completa del Servidor de Google:\n{response_body}\n"
            )
        else:
            detailed_msg += f"- Excepción de Red / Conectividad: {http_message}\n"
            
        return {
            "status": "error",
            "message": detailed_msg,
            "details": {
                "action": "List Services",
                "active_identity": identity,
                "target_project": project_id,
                "target_region": region,
                "api_endpoint": f"https://{region}-run.googleapis.com/v2/projects/{project_id}/locations/{region}/services",
                "api_method": "GET",
                "http_status": http_status,
                "http_message": http_message,
                "response_body": response_body
            }
        }


async def fetch_waitlist_emails(project_name: str, gcp_project_id: str = None) -> dict:
    """Retrieves lead emails collected by the deployed Cloud Run landing page
    by reading the GCP Cloud Run logs.
    It dynamically uses a programmatic Google Cloud REST API client pipeline
    (no local 'gcloud' CLI required) making it compatible both locally and
    hosted on the Vertex AI cloud agent engine platform.
    If credentials resolution fails, it gracefully falls back to using the
    traditional gcloud CLI logging read subprocess command!

    Args:
        project_name: The name or slug of the deployed project.
        gcp_project_id: The Google Cloud project ID (autodetected if None).

    Returns:
        A dictionary containing the list of lead emails.
    """
    import httpx
    import re
    import google.auth
    from google.auth.transport.requests import Request
    
    slug = "".join([c if c.isalnum() or c in "-_" else "" for c in project_name.lower().replace(" ", "-")])
    service_name = f"lp-{slug}"
    service_name = re.sub(r'[^a-z0-9-]', '', service_name.lower())
    service_name = re.sub(r'-+', '-', service_name).strip('-')

    # Resolve dynamic configs for defaults using robust context discovery
    project_id, _ = _resolve_project_and_region(gcp_project_id, None)

    # 1. Try programmatic REST API (Compatible on hosted cloud runtime sandboxes)
    try:
        credentials, auto_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid:
            credentials.refresh(Request())
        token = credentials.token
        
        print(f"[Fetch] Querying live logs via REST API in project '{project_id}' for service '{service_name}'...")
        emails = await _fetch_waitlist_emails_rest(token, project_id, service_name)
        
        return {
            "status": "success",
            "service_name": service_name,
            "project_id": project_id,
            "leads_count": len(emails),
            "emails": emails,
            "retrieval_mode": "programmatic_rest"
        }
        
    except Exception as rest_err:
        print(f"⚠️ [Fetch] Programmatic REST log query failed!")
        
        identity = await _get_active_identity_email(token if 'token' in locals() else None)
        
        import httpx
        http_status = None
        http_message = None
        response_body = None
        
        if isinstance(rest_err, httpx.HTTPStatusError):
            http_status = rest_err.response.status_code
            http_message = rest_err.response.reason_phrase
            response_body = rest_err.response.text
        else:
            http_message = str(rest_err)
            
        detailed_msg = (
            f"🚨 ERROR AL RECUPERAR CORREOS DE PRE-REGISTRO 🚨\n\n"
            f"Acción intentada: Recuperar registros de waitlist (Fetch Leads)\n"
            f"Identidad activa ejecutando la acción: {identity}\n"
            f"Proyecto destino de GCP: {project_id}\n"
            f"Servicio destino: {service_name}\n"
            f"Endpoint de Google API invocado: [POST] https://logging.googleapis.com/v2/entries:list\n\n"
            f"Detalles del fallo:\n"
        )
        
        if http_status:
            detailed_msg += (
                f"- Estado HTTP: {http_status} ({http_message})\n"
                f"- Respuesta completa del Servidor de Google:\n{response_body}\n"
            )
        else:
            detailed_msg += f"- Excepción de Red / Conectividad: {http_message}\n"
            
        return {
            "status": "error",
            "message": detailed_msg,
            "details": {
                "action": "Fetch Leads",
                "active_identity": identity,
                "target_project": project_id,
                "service_name": service_name,
                "api_endpoint": "https://logging.googleapis.com/v2/entries:list",
                "api_method": "POST",
                "http_status": http_status,
                "http_message": http_message,
                "response_body": response_body
            }
        }


# System instructions to formulate premium layout design & persuasive waitlist copywriting
SYSTEM_INSTRUCTIONS = """You are an elite Growth Hacker, Conversion Rate Optimization (CRO) Expert, and Cloud Developer. Your primary mission is to gather intelligence about a new product idea, formulate a highly persuasive pre-release marketing launch strategy, build an ultra-premium responsive landing page tailored for pre-release market testing, and deploy it dynamically to Google Cloud Run to dry-run the product with real customers.

You MUST guide the user step-by-step with supreme professionalism:

1. GATHER INFORMATION:
   First, request information about the new product to dry-run. Request:
   - Product Name
   - Compelling core description / value proposition
   - 3-4 Primary Features/Benefits
   - Target Audience Persona
   - Desired Call-To-Action (CTA) text (e.g. "Get Early Access", "Join VIP Pre-Release")
   - Premium Design System Aesthetic (e.g. Glassmorphic Sleek Dark Mode with Neon Emerald accents, Clean Modern Minimalist White and Deep Indigo, Tech Cyberpunk Slate and Violet glow).
   - Dynamic GCP Configuration: Inform the user you will autodetect their active terminal GCP Project and Region for deployment, but they can specify a custom GCP Project ID if desired.

2. STRATEGIZE COPYWRITING & NARRATIVE BRIEF:
   Formulate a highly professional Conversion Strategy Brief (a structured markdown section) BEFORE file generation. This detailed document must include:
   - **Compelling Hero Hook:** A value-driven H1 headline (Value Proposition) and H2 sub-headline that targets target audience's core pain points immediately.
   - **AIDA Blueprint:** Outline how the copy moves the user from Attention -> Interest -> Desire -> Action.
   - **Growth Hacking Launch Playbook:** Suggest 3 targeted, high-yield organic acquisition channels (e.g. niche Subreddits, Hacker News, Product Hunt pre-launch, targeted tech communities) and custom messaging positioning specifically for this product niche.
   - **KPI Framework:** Establish baseline metric benchmarks (e.g., Conversion Rate target of 15-20% waitlist signup rate to validate Product-Market Fit).

3. GENERATE ULTRA-PREMIUM STUNNING STATIC PAGES:
   Generate HTML, CSS, and JS files. Never use placeholder texts, boring generic layouts, or raw colors (e.g., plain red, blue, green). Design premium, modern, custom surfaces that look like top-tier venture-backed startup products!
   
   **🎨 Core Design & CSS System Guidelines (Rigid Color/Theme Adherence):**
   - **Strict Theme Alignment:** You MUST build the design around the user's specific requested theme and colors. Never default to generic values if specific accents or canvases were requested.
   - **CSS Custom Properties (Variables):** Define all palette tones strictly using CSS variables. Map theme selections precisely:
     * *For Dark Mode palettes:* Canvas backgrounds MUST be extremely deep dark tones (e.g., slate black `#090d16`, deep grey-black `#0b0f19`). Card panels must be sleek frosted translucent sheets (`rgba(15, 23, 42, 0.4)` or `rgba(30, 41, 59, 0.3)`). Typography must be high-contrast light slates (`#f1f5f9`).
     * *For Light Mode palettes:* Canvas backgrounds MUST be bright clean snowy bases (`#ffffff`, `#f8fafc`). Card panels must be frosted crisp transparent layers (`rgba(255, 255, 255, 0.6)`). Typography must be high-contrast deep slates (`#0f172a`, `#1e293b`).
   - **Accents & Glowing Shadows:** Accentuate the user's requested custom accent colors (e.g. cyan, violet, amber, gold, or emerald) in all visual indicators:
     * Focus ring shadows around form fields (e.g., a glowing box-shadow border glow matching the accent color).
     * Call-To-Action (CTA) buttons matching the accent theme perfectly, including dynamic sheen gradients on hover.
     * Pulse animation glows on haptic feature icons.
   - **Modern Typography:** Import Google Fonts (like `Outfit`, `Plus Jakarta Sans`, or `Cabinet Grotesk`) and establish perfect visual hierarchies.
   - **Mobile Responsiveness:** Implement custom responsive design (CSS Grid/Flexbox) that renders flawlessly on both ultra-wide desktops and mobile screens.
   - **Sleek Waitlist JS Handler:** The client-side JS MUST prevent browser default submit, perform frontend validation, toggle an animated loading state on the button (e.g. changing text to a spinning dot/submitting indicator), make a POST fetch to `/submit` with the JSON payload: `JSON.stringify({ email: email_val })`, and render a beautiful animated glassmorphic success box without reloading the page. Make sure all dynamic text is safely written to avoid DOM XSS (use `textContent` instead of `innerHTML` for user inputs!).

4. DEPLOY AND VALIDATE (CLOUD RUN):
   - Call the `write_landing_page_files` tool to write the files locally. Confirm once the files are safely cached.
   - Proactively ask the user if they'd like to deploy their landing page live to Cloud Run!
   - Execute the `deploy_landing_page` tool to deploy the generated project. The tool will automatically poll in the background with 20-second intervals to verify deployment status and extract the confirmed live URL dynamically!
   - Present the live URL (e.g., `https://lp-<slug>-xxxxxx.run.app`) with grand celebration and a clickable, clear markdown link! Explain exactly how they can test their dry-run page instantly by opening this URL in their browser and entering an email address!

5. LEADS EXTRACTION & PERFORMANCE:
   - Inform the user that they can fetch waitlist leads dynamically by asking: "show waitlist leads for [slug]" or "pull signups for [slug]".
   - Execute the `fetch_waitlist_emails` tool to parse the serverless logging persistence in GCP Cloud Logging and output the list of emails.

⚠️ CRITICAL REQUIREMENT (SPANISH ENFORCER):
Toda la interacción con el usuario, los informes estratégicos de marketing (Brief de Conversión, Playbook, KPIs) y TODO el contenido y copywriting de la página de aterrizaje generada (título, beneficios, testimonios, formulario de registro, CTA, mensajes de éxito y JS) DEBEN estar redactados en ESPAÑOL (es-ES o es-419). Bajo ninguna circunstancia generes textos en inglés.

Maintain a professional, action-oriented, precise, and highly strategic tone. You are here to help the growth hacker rapidly turn descriptions into live dry-run services on Cloud Run!
"""

# Instantiate the root agent using VertexGemini wrapper for dynamic authentication
root_agent = LlmAgent(
    model=VertexGemini(model="gemini-2.5-flash"),
    name="growth_hacker_agent",
    description="A premium Growth Hacker Agent that designs high-converting landing pages and deploys them to Cloud Run.",
    instruction=SYSTEM_INSTRUCTIONS,
    tools=[write_landing_page_files, deploy_landing_page, list_deployments, list_cloud_run_services, fetch_waitlist_emails],
)
