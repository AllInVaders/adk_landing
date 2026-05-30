import os
import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

# Get the directory where main.py is located
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Use a SQLite database for managing persistent agent chat sessions
SESSION_SERVICE_URI = "sqlite+aiosqlite:///./sessions.db"

# Allow CORS for easy browser access
ALLOWED_ORIGINS = ["*"]

# Enable the built-in interactive developer UI
SERVE_WEB_INTERFACE = True

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_SERVICE_URI,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting local Growth Hacker Agent Web UI at http://localhost:{port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
