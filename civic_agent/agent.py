"""
civic_agent/agent.py
--------------------
Civic Action Agent — built with Google ADK SequentialAgent.

Pipeline:
  1. IssueAnalyzerAgent  — uses Gemini 2.0 Flash to classify & analyse the issue.
  2. ReportRegistrarAgent — calls the report_validator tool to register the issue
                            with the simulated Government portal.
"""
import sys
import os

# ---------------------------------------------------------------------------
# Make sure the project root is on the path so `tools` is importable.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents import Agent, SequentialAgent
from tools.report_validator import report_validator

# ---------------------------------------------------------------------------
# Sub-agent 1 — Issue Analyser
# ---------------------------------------------------------------------------
issue_analyzer_agent = Agent(
    model="gemini-2.0-flash",
    name="issue_analyzer_agent",
    description=(
        "Analyses a civic issue described in text or via an image URL "
        "and produces a structured JSON report with Category, Severity, "
        "Location, and Description fields."
    ),
    instruction="""You are an expert Civic Issue Analyst working for a Smart City platform.

Your job is to look at the user's message (which may include an image description
or an image URL) and extract the following details:

- **Category**: One of [Pothole, Broken Streetlight, Garbage Overflow, Water Leakage,
  Damaged Road Sign, Encroachment, Flooding, Other]
- **Severity**: One of [Low, Medium, High, Critical]
  - Low    → Minor inconvenience, no safety risk
  - Medium → Moderate disruption, some safety concern
  - High   → Significant hazard, immediate attention needed
  - Critical → Life-threatening or major infrastructure failure
- **Location**: Specific street address, intersection, or landmark. If unavailable
  write "Location not specified".
- **Description**: A concise 1–2 sentence summary of the problem.

Respond ONLY with a valid JSON object in this exact format:
{
  "category": "<Category>",
  "severity": "<Severity>",
  "location": "<Location>",
  "description": "<Description>"
}

Do not include any additional text, markdown, or code fences.
""",
    output_key="issue_analysis",
)

# ---------------------------------------------------------------------------
# Sub-agent 2 — Report Registrar
# ---------------------------------------------------------------------------
report_registrar_agent = Agent(
    model="gemini-2.0-flash",
    name="report_registrar_agent",
    description=(
        "Reads the structured issue analysis from the session state and calls "
        "the report_validator tool to register the civic complaint."
    ),
    instruction="""You are a Civic Report Registrar.

You have access to the variable `{issue_analysis}` that contains a JSON string
produced by the Issue Analyser. Parse it and call the `report_validator` tool
with the extracted fields:
  - category
  - severity
  - location
  - description

After receiving the tool response, generate a friendly, professional summary for
the citizen. Include:
  - The Government Tracking ID
  - The registered category and severity
  - The location
  - The estimated resolution time
  - A reassuring closing statement

Keep your response within 120 words.
""",
    tools=[report_validator],
    output_key="registration_result",
)

# ---------------------------------------------------------------------------
# Root SequentialAgent — orchestrates the two sub-agents in order
# ---------------------------------------------------------------------------
root_agent = SequentialAgent(
    name="civic_action_agent",
    description=(
        "End-to-end civic issue reporting pipeline: analyses the issue with "
        "Gemini 2.0 Flash, then registers it with the Government portal."
    ),
    sub_agents=[issue_analyzer_agent, report_registrar_agent],
)
