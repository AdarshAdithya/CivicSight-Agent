# 🏛️ CivicSight — Civic Action Agent

> **Production-ready AI-powered civic issue reporting pipeline built with Google ADK, Gemini 2.0 Flash, and FastAPI.**

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/) [![Google ADK](https://img.shields.io/badge/Google%20ADK-1.0-4285F4.svg)](https://google.github.io/adk-docs/) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/) [![Cloud Run Ready](https://img.shields.io/badge/Cloud%20Run-Ready-34A853.svg)](https://cloud.google.com/run)

---

## Architecture

```
User (Streamlit UI)
        │
        ▼
FastAPI /chat endpoint (main.py)
        │
        ▼
ADK Runner → SequentialAgent
        │
        ├─► IssueAnalyzerAgent  (Gemini 2.0 Flash)
        │       Classifies: Category, Severity, Location, Description
        │
        └─► ReportRegistrarAgent (Gemini 2.0 Flash + report_validator tool)
                Calls report_validator → returns GOV-XXXXXXXX Tracking ID
```

## Project Structure

```
CivicSight-Agent/
├── civic_agent/
│   ├── __init__.py
│   └── agent.py          # SequentialAgent definition
├── tools/
│   ├── __init__.py
│   └── report_validator.py  # ADK tool → Government Tracking ID
├── frontend/
│   └── app.py            # Streamlit UI
├── main.py               # FastAPI app
├── requirements.txt
├── pyproject.toml        # uv project config
├── Dockerfile
├── .dockerignore
└── .env.example
```

---

## Quick Start (Local Development)

### 1. Install uv

```bash
pip install uv
```

### 2. Create & activate virtual environment

```bash
uv venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
uv pip install -r requirements.txt
```

### 4. Configure credentials

```bash
# Copy the template
cp .env.example .env
```

Edit `.env` and set your **Google AI Studio API key**:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

> Get a free key at [aistudio.google.com](https://aistudio.google.com/apikey)

### 5. Start the FastAPI backend

```bash
uvicorn main:app --reload --port 8001
```

- API docs: [http://localhost:8001/docs](http://localhost:8001/docs)
- Health check: [http://localhost:8001/health](http://localhost:8001/health)

### 6. Start the Streamlit frontend (new terminal)

```bash
streamlit run frontend/app.py
```

---

## API Reference

### `GET /health`
Liveness probe — returns `{"status": "ok"}`.

### `POST /chat`

**Request body:**
```json
{
  "message": "Large pothole on MG Road near City Mall",
  "image_url": "https://example.com/pothole.jpg",
  "session_id": null
}
```

**Response:**
```json
{
  "session_id": "uuid-...",
  "tracking_id": "GOV-A1B2C3D4",
  "reply": "Your issue has been registered! Tracking ID: GOV-A1B2C3D4 ..."
}
```

---

## ☁️ Deploy to Google Cloud Run

### Prerequisites

```bash
# Install Google Cloud SDK and authenticate
gcloud auth login
gcloud auth configure-docker
```

### One-time project setup

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export SERVICE_NAME="civicsight-agent"

gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com \
                       cloudbuild.googleapis.com \
                       artifactregistry.googleapis.com
```

### Build & push the container

```bash
# Build with Cloud Build (no local Docker needed)
gcloud builds submit \
  --tag gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --project $PROJECT_ID
```

### Deploy to Cloud Run

```bash
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="your_api_key_here" \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --project $PROJECT_ID
```

> 💡 **Vertex AI (recommended for production)**: Replace `GOOGLE_API_KEY` with:
> ```bash
> --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true
> ```
> and grant the `roles/aiplatform.user` IAM role to your Cloud Run service account.

### Get the service URL

```bash
gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format "value(status.url)"
```

### Health check the deployed service

```bash
curl "$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)')/health"
```

### Deploy the Streamlit UI (Cloud Run – optional)

```bash
gcloud run deploy civicsight-frontend \
  --source frontend/ \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars BACKEND_URL="https://$SERVICE_NAME-xxxx-uc.a.run.app" \
  --port 8501 \
  --project $PROJECT_ID
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes (AI Studio) | Gemini API key from AI Studio |
| `GOOGLE_CLOUD_PROJECT` | Yes (Vertex AI) | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Yes (Vertex AI) | GCP region (e.g. `us-central1`) |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes (Vertex AI) | Set to `true` |
| `PORT` | No | Server port (default: `8080`) |

---

## Development

```bash
# Lint
uv pip install ruff
ruff check .

# Tests (add test files to tests/)
uv pip install pytest httpx
pytest

# ADK Developer UI (visualise agent pipeline)
adk web
```

---

## License

MIT © CivicSight Team
