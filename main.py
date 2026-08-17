"""
main.py
-------
FastAPI application for CivicSight — Civic Action Agent.

Uses Google ADK SequentialAgent with Gemini 2.0 Flash to analyse civic issues
and register them with a simulated Government portal.
"""
import os
import uuid
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from civic_agent.agent import root_agent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civic_action_agent")

APP_NAME = "civic_action_agent"

# ---------------------------------------------------------------------------
# ADK Runner — initialised once at startup
# ---------------------------------------------------------------------------
session_service: InMemorySessionService = None
runner: Runner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_service, runner

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY environment variable is not set. "
            "Get a free key at https://aistudio.google.com/apikey"
        )

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )
    logger.info(
        "✅  ADK Runner initialised — agent='%s', model='gemini-3.5-flash'",
        root_agent.name,
    )
    yield
    logger.info("🛑  Shutting down Civic Action Agent API")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CivicSight — Civic Action Agent API",
    description=(
        "Production-ready civic issue reporting powered by "
        "Google ADK + Gemini 2.0 Flash."
    ),
    version="2.0.0",
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
# Helpers
# ---------------------------------------------------------------------------
def _extract_tracking_id(text: str) -> Optional[str]:
    """Extract GOV-XXXXXXXX tracking ID from agent reply text."""
    match = re.search(r"GOV-[A-F0-9]{8}", text)
    return match.group(0) if match else None


def _parse_issue_analysis(raw: str) -> Optional[dict]:
    """Safely parse the JSON string stored by IssueAnalyzerAgent in session state."""
    if not raw:
        return None
    try:
        clean = re.sub(r"^```(?:json)?\s*", "", str(raw).strip())
        clean = re.sub(r"\s*```$", "", clean)
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Could not parse issue_analysis JSON: %s", raw)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Ops"])
async def health_check():
    """Liveness probe — used by Cloud Run / Vercel."""
    return {"status": "ok", "agent": APP_NAME, "model": "gemini-3.5-flash"}


@app.get("/", response_class=HTMLResponse, tags=["Ops"])
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"), status_code=200)


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(request: ChatRequest):
    """
    Run the CivicSight SequentialAgent pipeline:
      1. IssueAnalyzerAgent  — classifies the civic issue (Gemini 2.0 Flash)
      2. ReportRegistrarAgent — registers via report_validator tool (Gemini 2.0 Flash)
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session_id = request.session_id or str(uuid.uuid4())
    user_id = "citizen"

    # Attach image URL hint if provided
    user_input = request.message
    if request.image_url:
        user_input += f"\n[Image reference for analysis]: {request.image_url}"

    # -----------------------------------------------------------------------
    # Create ADK session for this request
    # -----------------------------------------------------------------------
    try:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        logger.info("ADK session created: %s", session_id)
    except Exception as exc:
        # Session may already exist if the same session_id is reused
        logger.warning("Session create notice (may already exist): %s", exc)

    # -----------------------------------------------------------------------
    # Run the full ADK SequentialAgent pipeline
    # -----------------------------------------------------------------------
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=user_input)],
    )

    final_reply = ""
    last_exc = None
    for attempt in range(3):
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                # Capture the last final response (emitted by ReportRegistrarAgent)
                if event.is_final_response() and event.content and event.content.parts:
                    text = event.content.parts[0].text
                    if text:
                        final_reply = text
                        logger.info("ADK final event — %d chars", len(final_reply))
            break  # success — exit retry loop
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                wait = 5 * (attempt + 1)
                logger.warning(
                    "Transient error (attempt %d/3), retrying in %ds: %s",
                    attempt + 1, wait, err_str[:120],
                )
                import asyncio
                await asyncio.sleep(wait)
            else:
                logger.exception("ADK runner.run_async failed (non-retryable)")
                raise HTTPException(
                    status_code=500, detail=f"Agent pipeline failed: {exc}"
                )
    else:
        logger.exception("ADK runner.run_async failed after 3 retries")
        raise HTTPException(
            status_code=503, detail=f"Model temporarily unavailable. Please try again: {last_exc}"
        )

    # -----------------------------------------------------------------------
    # Read structured outputs from ADK session state
    # -----------------------------------------------------------------------
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    # IssueAnalyzerAgent stores JSON → session.state["issue_analysis"]
    issue_data = _parse_issue_analysis(
        session.state.get("issue_analysis", "") if session else ""
    )
    logger.info("issue_analysis: %s", issue_data)

    # ReportRegistrarAgent stores friendly text → session.state["registration_result"]
    registration_result = (
        session.state.get("registration_result", "") if session else ""
    )
    reply_text = str(registration_result).strip() if registration_result else final_reply

    # Extract the GOV-XXXXXXXX tracking ID embedded in the reply text
    tracking_id = _extract_tracking_id(reply_text)
    if tracking_id:
        logger.info("Tracking ID: %s", tracking_id)
    else:
        logger.warning("No tracking ID found in reply — check ReportRegistrarAgent output")

    return ChatResponse(
        session_id=session_id,
        tracking_id=tracking_id,
        issue_analysis=issue_data,
        reply=reply_text or "Issue registered successfully. Please check back later.",
    )
