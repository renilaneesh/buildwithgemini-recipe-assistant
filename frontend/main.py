"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
clean, structured parts (text bubbles or A2UI cards) with all ADK/tracing metadata filtered out.
"""

import asyncio
import json
import os
import re

import google.auth
import google.auth.transport.requests
import httpx
from a2a.types import AgentCard
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/qwiklabs-gcp-01-1a15618a3a67/locations/us-east1/reasoningEngines/5593939129147588608",
)
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"
REMOTE_ENGINE_URL = f"https://{LOCATION}-aiplatform.googleapis.com/v1/{RESOURCE}"

_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient | None = None, default_url: str = "http://localhost:8080") -> AgentCard:
    """Fetch or create AgentCard ensuring required url field is provided."""
    global _card
    if _card is None:
        card_dict = {}
        if client is not None:
            try:
                resp = await client.get(A2A_CARD_URL)
                if resp.status_code == 200:
                    card_dict = resp.json()
            except Exception:
                card_dict = {}

        if isinstance(card_dict, dict):
            if not card_dict.get("url"):
                interfaces = card_dict.get("supportedInterfaces") or []
                if interfaces and isinstance(interfaces, list) and isinstance(interfaces[0], dict) and interfaces[0].get("url"):
                    card_dict["url"] = interfaces[0]["url"]
                else:
                    card_dict["url"] = default_url or A2A_BASE
            if not card_dict.get("name"):
                card_dict["name"] = "recipe-assistant"
            card = AgentCard(**card_dict)
        else:
            card = AgentCard(url=default_url or A2A_BASE, name="recipe-assistant")
        
        card.url = A2A_BASE
        _card = card
    return _card


def _clean_text_segment(text: str) -> str:
    """Strip raw protobuf / ADK metadata / tracing blocks from plain text."""
    for marker in ["artifact_update {", "status_update {", "metadata {", "task_id:", "context_id:"]:
        if marker in text:
            text = text.split(marker)[0]
    clean_lines = []
    for line in text.splitlines():
        if any(bad in line for bad in ["adk_user_id", "adk_session_id", "adk_invocation_id", "adk_event_id", "adk_author", "adk_app_name", "TASK_STATE_"]):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def _parse_text_for_a2ui(text: str) -> list[dict]:
    """Parse text for embedded <a2ui-json> blocks and separate them into clean A2UI/text parts."""
    out = []
    pattern = r"<a2ui-json>([\s\S]*?)</a2ui-json>"
    last_idx = 0
    for match in re.finditer(pattern, text):
        pre_text = _clean_text_segment(text[last_idx:match.start()])
        if pre_text:
            out.append({"kind": "text", "text": pre_text})
        try:
            data = json.loads(match.group(1))
            out.append({"kind": "a2ui", "data": data})
        except Exception:
            pass
        last_idx = match.end()
    post_text = _clean_text_segment(text[last_idx:])
    if post_text:
        out.append({"kind": "text", "text": post_text})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    session_id = _contexts.get(user_id)
    base_url = str(req.base_url).rstrip("/")

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=30) as http_client:
        await _get_card(http_client, default_url=base_url)

    cmd = ["agents-cli", "run", "--url", REMOTE_ENGINE_URL, "--mode", "a2a", "-v", message]
    if session_id:
        cmd.extend(["--session-id", session_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out_str = stdout.decode()

    parts: list[dict] = []
    
    # Save session context for follow-up turns
    m_sess = re.search(r"Session:\s+([a-f0-9\-]+)", out_str)
    if m_sess:
        _contexts[user_id] = m_sess.group(1)

    # Extract A2UI JSON payload blocks from verbose CLI output
    json_blocks = re.findall(r"^(\{\s*\n[\s\S]*?\n\s*\})", out_str, re.MULTILINE)
    for block in json_blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                art_up = data.get("artifact_update") or data.get("artifactUpdate")
                if art_up:
                    art = art_up.get("artifact", {})
                    for p in art.get("parts", []):
                        if "data" in p:
                            parts.append({"kind": "a2ui", "data": p["data"]})
                        elif "text" in p:
                            parts.extend(_parse_text_for_a2ui(p["text"]))
        except Exception:
            pass

    # Extract text content if no A2UI cards were extracted from verbose logs
    if not parts:
        lines = []
        capturing = False
        for line in out_str.splitlines():
            if line.startswith("[agent]: "):
                lines.append(line[9:])
                capturing = True
            elif any(prefix in line for prefix in [
                "Querying remote agent", "[user]:", "Session:", "  Resume with:", "Artifacts:",
                "artifact_update", "status_update", "metadata {", "task_id:", "context_id:", "adk_"
            ]):
                capturing = False
            elif capturing:
                lines.append(line)
        if lines:
            raw_text = "\n".join(lines).strip()
            parts.extend(_parse_text_for_a2ui(raw_text))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]

    return JSONResponse({"parts": parts})


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_file) and os.path.exists(os.path.join(TEMPLATES_DIR, "index.html")):
        index_file = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
