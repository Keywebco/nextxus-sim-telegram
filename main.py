"""Telegram webhook bridge to the Roger Sim API."""

import hmac
import logging
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Roger Sim Telegram")
logger = logging.getLogger(__name__)
FALLBACK = "The Sim is thinking... try again in a moment."


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not secret or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
        return {"ok": True}
    chat = message.get("chat")
    if not isinstance(chat, dict) or not isinstance(chat.get("id"), int):
        return {"ok": True}
    text = message["text"].strip()
    if not text:
        return {"ok": True}

    token = os.environ.get("ROGER_SIM_TELEGRAM_TOKEN")
    backend_url = os.environ.get("SIM_BACKEND_URL", "").rstrip("/")
    backend_token = os.environ.get("SIM_BACKEND_TOKEN")
    if not token or not backend_url or not backend_token:
        logger.error("Roger Sim webhook configuration missing")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    chat_id = chat["id"]
    try:
        async with httpx.AsyncClient(timeout=100.0) as client:
            response = await client.post(
                f"{backend_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {backend_token}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": text}],
                    "stream": False,
                    "session_id": str(chat_id),
                },
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty response from Roger Sim")
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        logger.exception("Roger Sim backend request failed")
        answer = FALLBACK

    # Telegram rejects messages longer than 4096 characters. Keep chunks independent of markup.
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for start in range(0, len(answer), 4096):
                delivery = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": answer[start:start + 4096]},
                )
                delivery.raise_for_status()
                if not delivery.json().get("ok"):
                    raise ValueError("Telegram rejected sendMessage")
    except (httpx.HTTPError, ValueError):
        logger.exception("Telegram sendMessage failed")
        raise HTTPException(status_code=502, detail="Telegram delivery failed")
    return {"ok": True}
