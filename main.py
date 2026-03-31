"""
main.py
-------
FastAPI application for CivicSight — Civic Action Agent.

Uses Groq (Llama-3) to bypass region locks and free-tier quotas on Google APIs.
"""
import os
import uuid
import json
import logging
import re
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from groq import AsyncGroq
from groq import InternalServerError, RateLimitError

from tools.report_validator import report_validator

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civic_action_agent")

# ---------------------------------------------------------------------------
# Groq setup (initialised once at startup)
# ---------------------------------------------------------------------------
MODEL = "llama-3.3-70b-versatile"
client: AsyncGroq = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Set it before starting the server."
        )
    client = AsyncGroq(api_key=api_key)
    logger.info("✅  Groq client initialised with model='%s'", MODEL)
    yield
    logger.info("🛑  Shutting down Civic Action Agent API")


async def _generate_with_retry(messages: list, response_format=None, max_retries: int = 3) -> str:
    """Helper to bypass free-tier rate limits with exponential backoff retries."""
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": MODEL,
                "messages": messages,
                "temperature": 0.1,
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except (RateLimitError, InternalServerError) as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = 3 * (2 ** attempt)
            logger.warning("Rate limit hit! Retrying in %ds... (attempt %d/%d)", wait_time, attempt+1, max_retries)
            await asyncio.sleep(wait_time)


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CivicSight — Civic Action Agent API",
    description="Production-ready civic issue reporting powered by Groq Llama 3.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    image_url: Optional[str] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    tracking_id: Optional[str] = None
    issue_analysis: Optional[dict] = None
    reply: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Ops"])
async def health_check():
    """Liveness probe — used by Cloud Run."""
    return {"status": "ok", "agent": "civic_action_agent", "model": MODEL}


@app.get("/", tags=["Ops"])
async def root():
    return {
        "service": "CivicSight Civic Action Agent",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session_id = request.session_id or str(uuid.uuid4())

    user_input = request.message
    if request.image_url:
        user_input += f"\n[Image reference for analysis]: {request.image_url}"

    # -----------------------------------------------------------------------
    # STEP 1 — Issue Analyser
    # -----------------------------------------------------------------------
    analyzer_prompt = f"""You are an expert Civic Issue Analyst for a Smart City platform.

Analyse the following civic issue and extract these details:
- Category: One of [Pothole, Broken Streetlight, Garbage Overflow, Water Leakage, Damaged Road Sign, Encroachment, Flooding, Other]
- Severity: One of [Low, Medium, High, Critical]
- Location: Street address or landmark. If unknown, write "Location not specified".
- Description: 1-2 sentence summary.

Respond ONLY with a valid JSON object matching this schema absolutely perfectly:
{{"category": "...", "severity": "...", "location": "...", "description": "..."}}

Civic issue to analyse:
{user_input}"""

    raw_analysis = ""
    try:
        messages = [{"role": "user", "content": analyzer_prompt}]
        # Use Groq's JSON mode ensuring flawless JSON outputs
        raw_analysis = await _generate_with_retry(messages, response_format={"type": "json_object"})
        raw_analysis = raw_analysis.strip()

        # Strip markdown fences just in case
        raw_analysis = re.sub(r"^```(?:json)?\s*", "", raw_analysis)
        raw_analysis = re.sub(r"\s*```$", "", raw_analysis)

        issue_data = json.loads(raw_analysis)
        logger.info("Step 1 — IssueAnalyzer: %s", issue_data)

    except json.JSONDecodeError:
        logger.warning("Step 1 — JSON parse failed, using defaults. Raw: %s", raw_analysis)
        issue_data = {
            "category": "Other",
            "severity": "Medium",
            "location": "Location not specified",
            "description": request.message[:200],
        }
    except Exception as exc:
        logger.exception("Step 1 — IssueAnalyzer failed")
        raise HTTPException(status_code=500, detail=f"Issue analysis failed: {exc}")

    # -----------------------------------------------------------------------
    # STEP 2 — Report Registrar (call report_validator tool)
    # -----------------------------------------------------------------------
    try:
        tool_result = report_validator(
            category=issue_data.get("category", "Other").title(),
            severity=issue_data.get("severity", "Medium").title(),
            location=issue_data.get("location", "Location not specified"),
            description=issue_data.get("description", request.message[:200]),
        )
        tracking_id = tool_result["tracking_id"]
        logger.info("Step 2 — report_validator: tracking_id=%s", tracking_id)
    except Exception as exc:
        logger.exception("Step 2 — report_validator failed")
        raise HTTPException(status_code=500, detail=f"Report registration failed: {exc}")

    # -----------------------------------------------------------------------
    # STEP 3 — Generate friendly citizen summary
    # -----------------------------------------------------------------------
    summary_prompt = f"""You are a Civic Report Registrar for a Smart City portal.

A civic issue has been successfully registered. Generate a warm, professional 
summary for the citizen in under 120 words. Include:
- Government Tracking ID: {tracking_id}
- Issue category and severity
- Location: {tool_result['location']}
- Estimated resolution: {tool_result['estimated_resolution_days']} day(s)
- A reassuring closing statement

Issue details: {json.dumps(tool_result)}"""

    try:
        messages = [{"role": "user", "content": summary_prompt}]
        reply_text = await _generate_with_retry(messages)
        reply_text = reply_text.strip()
        logger.info("Step 3 — Summary generated (%d chars)", len(reply_text))
    except Exception as exc:
        logger.exception("Step 3 — Summary generation failed")
        reply_text = tool_result["message"]

    return ChatResponse(
        session_id=session_id,
        tracking_id=tracking_id,
        issue_analysis=issue_data,
        reply=reply_text,
    )
