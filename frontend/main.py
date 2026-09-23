import asyncio
import json
import os
import re
import sys
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure frontend directory and root directory are in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

app = FastAPI(title="Recipe Assistant Proxy Frontend")

REMOTE_ENGINE_URL = os.getenv(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/qwiklabs-gcp-01-1a15618a3a67/locations/us-east1/reasoningEngines/5593939129147588608",
)

_card: Dict[str, Any] | None = None
_contexts: Dict[str, str] = {}


def _auth_headers() -> dict[str, str]:
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return {"Authorization": f"Bearer {creds.token}"}


async def _get_card(
    http_client: httpx.AsyncClient, default_url: str = "http://localhost:8080"
) -> Dict[str, Any]:
    global _card
    if _card is None:
        try:
            r = await http_client.get(
                f"{REMOTE_ENGINE_URL.rstrip('/')}/.well-known/agent-card.json"
            )
            r.raise_for_status()
            card = r.json()
            if not card.get("url"):
                card["url"] = default_url
        except Exception:
            card = {
                "name": "Recipe Assistant Agent",
                "description": "Culinary AI assistant powered by Gemini and ADK.",
                "url": default_url,
                "version": "1.0.0",
                "capabilities": {},
            }
        _card = card
    return _card


def _clean_text_segment(text: str) -> str:
    """Strip raw protobuf / ADK metadata / tracing blocks from plain text."""
    if not text:
        return ""
    for marker in [
        "artifact_update {",
        "status_update {",
        "metadata {",
        "task_id:",
        "context_id:",
    ]:
        if marker in text:
            text = text.split(marker)[0]
    clean_lines = []
    for line in text.splitlines():
        if any(
            bad in line
            for bad in [
                "adk_user_id",
                "adk_session_id",
                "adk_invocation_id",
                "adk_event_id",
                "adk_author",
                "adk_app_name",
                "TASK_STATE_",
            ]
        ):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def _parse_text_for_a2ui(text: str) -> list[dict]:
    """Parse text for embedded A2UI JSON structures or <a2ui-json> blocks."""
    out = []
    raw_trim = text.strip()
    if raw_trim.startswith("{") and raw_trim.endswith("}"):
        try:
            parsed = json.loads(raw_trim)
            if isinstance(parsed, dict):
                data_obj = parsed.get("data") if "data" in parsed else parsed
                if isinstance(data_obj, dict) and (
                    "surfaceUpdate" in data_obj
                    or "beginRendering" in data_obj
                    or "components" in data_obj
                ):
                    return [{"kind": "a2ui", "data": data_obj}]
        except Exception:
            pass

    clean = _clean_text_segment(text)
    if not clean:
        return out

    pattern = r"(\{\s*\n?[\s\S]*?\"surfaceUpdate\"[\s\S]*?\n?\})"
    last_idx = 0
    for match in re.finditer(pattern, clean):
        pre_text = _clean_text_segment(clean[last_idx : match.start()])
        if pre_text:
            out.append({"kind": "text", "text": pre_text})
        try:
            data = json.loads(match.group(1))
            data_obj = (
                data.get("data") if isinstance(data, dict) and "data" in data else data
            )
            out.append({"kind": "a2ui", "data": data_obj})
        except Exception:
            pass
        last_idx = match.end()

    if last_idx > 0:
        post_text = _clean_text_segment(clean[last_idx:])
        if post_text:
            out.append({"kind": "text", "text": post_text})
        return out

    return [{"kind": "text", "text": clean}]


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    session_id = _contexts.get(user_id)
    base_url = str(req.base_url).rstrip("/")

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=30) as http_client:
        await _get_card(http_client, default_url=base_url)

    cmd = [
        "agents-cli",
        "run",
        "--url",
        REMOTE_ENGINE_URL,
        "--mode",
        "a2a",
        "-v",
        message,
    ]
    if session_id:
        cmd.extend(["--session-id", session_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
            elif any(
                prefix in line
                for prefix in [
                    "Querying remote agent",
                    "[user]:",
                    "Session:",
                    "  Resume with:",
                    "Artifacts:",
                    "artifact_update",
                    "status_update",
                    "metadata {",
                    "task_id:",
                    "context_id:",
                    "adk_",
                ]
            ):
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
    if not os.path.exists(index_file) and os.path.exists(
        os.path.join(TEMPLATES_DIR, "index.html")
    ):
        index_file = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
