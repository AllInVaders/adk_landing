import os
import logging
from fastapi import FastAPI
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

@app.post("/submit")
async def submit_email(lead: LeadSubmission):
    email = lead.email.strip().lower()
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
