import os
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
