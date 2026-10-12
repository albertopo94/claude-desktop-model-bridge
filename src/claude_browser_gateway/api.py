"""FastAPI gateway exposing Claude session over standard APIs."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .config import Settings
from .auth import AuthManager
from .chat import ChatSession
from .queue import RequestQueue, TokenBudget
from .version_gate import VersionGate

app = FastAPI(title="Claude Browser Gateway")
settings = Settings.from_env()
auth_manager: AuthManager | None = None
chat_session: ChatSession | None = None
queue: RequestQueue = RequestQueue()
gate: VersionGate | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    max_tokens: int | None = 1000
    temperature: float | None = 0.7
    stream: bool = False


class AnthropicMessageRequest(BaseModel):
    model: str
    max_tokens: int
    messages: list[dict[str, Any]]
    system: str | None = None
    stream: bool = False
    temperature: float | None = 0.7


@app.on_event("startup")
async def startup_event() -> None:
    global auth_manager, chat_session, gate
    auth_manager = AuthManager(settings)
    await auth_manager.start()
    chat_session = ChatSession(auth_manager, settings)
    gate = VersionGate(fingerprint_file=settings.session_dir / "version_gate.json")
    auth_ok = await auth_manager.is_authenticated()
    if not auth_ok:
        print("[gateway] Not authenticated to claude.ai — run 'claude-browser-gateway login' first.")


@app.get("/health")
async def health() -> dict:
    auth_ok = await (auth_manager.is_authenticated() if auth_manager else False)
    return {
        "status": "ok" if auth_ok else "auth_required",
        "session_dir": str(settings.session_dir),
        "claude_url": settings.claude_url,
        "version": "0.1.0",
        "supported_desktop_version": "2.31226.1 (857652)",
    }


@app.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": "claude-haiku-4-5-20251001", "object": "model", "created": 0, "owned_by": "claude"},
            {"id": "claude-sonnet-4-6-20251001", "object": "model", "created": 0, "owned_by": "claude"},
            {"id": "claude-opus-4-5-20251001", "object": "model", "created": 0, "owned_by": "claude"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest) -> Response:
    if auth_manager is None or not await auth_manager.is_authenticated():
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Not authenticated. Run 'claude-browser-gateway login'.", "type": "authentication_error"}},
        )

    # Estimate tokens for rate limiting (conservative: 4 chars/token)
    total_chars = sum(len(str(m.get("content", ""))) for m in req.messages)
    estimated_tokens = max(1, total_chars // 4) + (req.max_tokens or 500)
    await queue.acquire(estimated_tokens)

    # Convert conversation turns into chat session
    assert chat_session
    for m in req.messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str):
            chat_session.add_turn(role, content)

    # Last user message is what we actually drive into the chat UI
    last_user = next((m.get("content", "") for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not last_user:
        return JSONResponse(status_code=400, content={"error": {"message": "No user message in conversation.", "type": "invalid_request_error"}})

    if req.stream:
        async def event_generator():
            async for delta in chat_session.stream(last_user):
                chunk = {
                    "id": f"chatcmpl-{int(time.time()*1000)}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model or "claude-haiku-4-5-20251001",
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            # Final chunk with finish_reason
            final_chunk = {
                "id": f"chatcmpl-{int(time.time()*1000)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": req.model or "claude-haiku-4-5-20251001",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final_chunk)}\n\ndata: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming
    response_text = await chat_session.send(last_user)
    return JSONResponse(content={
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or "claude-haiku-4-5-20251001",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response_text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": estimated_tokens, "completion_tokens": len(response_text)//4, "total_tokens": estimated_tokens + len(response_text)//4},
    })


@app.post("/v1/messages")
async def messages(req: AnthropicMessageRequest) -> Response:
    if auth_manager is None or not await auth_manager.is_authenticated():
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Not authenticated. Run 'claude-browser-gateway login'.", "type": "authentication_error"}},
        )

    # Estimate tokens
    total_chars = sum(len(str(m.get("content", ""))) for m in req.messages) + len(req.system or "")
    estimated_tokens = max(1, total_chars // 4) + req.max_tokens
    await queue.acquire(estimated_tokens)

    assert chat_session
    if req.system:
        chat_session.add_turn("system", req.system)
    for m in req.messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str):
            chat_session.add_turn(role, content)

    last_user = next((m.get("content", "") for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not last_user:
        return JSONResponse(status_code=400, content={"error": {"message": "No user message in conversation.", "type": "invalid_request_error"}})

    if req.stream:
        async def event_generator():
            # Anthropic Messages SSE format
            yield 'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","content":[],"model":"' + req.model + '"}}\n\n'
            yield 'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
            async for delta in chat_session.stream(last_user):
                yield 'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":' + json.dumps(delta) + '}}\n\n'
            yield 'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
            yield 'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":10}}\n\n'
            yield 'event: message_stop\ndata: {"type":"message_stop"}\n\n'
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    response_text = await chat_session.send(last_user)
    return JSONResponse(content={
        "id": f"msg_{int(time.time()*1000)}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": response_text}],
        "model": req.model,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": estimated_tokens, "output_tokens": len(response_text)//4},
    })


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if auth_manager:
        await auth_manager.stop()
