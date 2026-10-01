# Roger Sim — Telegram bridge

A Telegram webhook forwarding messages to the live Roger Sim API. It has no database; every message is independent (the backend does not currently support session history).

## Deployment

Create a Render Python web service from this repository, branch `main`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set these **secret** environment variables in Render (never commit their values):

- `ROGER_SIM_TELEGRAM_TOKEN`: Telegram bot token.
- `TELEGRAM_WEBHOOK_SECRET`: random URL-safe secret sent in Telegram's `X-Telegram-Bot-Api-Secret-Token` header.
- `SIM_BACKEND_URL`: `https://roger-sim-api.onrender.com` (live Render URL).
- `SIM_BACKEND_TOKEN`: existing `BRIDGE_TOKEN` from the Roger Sim API Render service.

When Render reports the service URL, register `https://<render-host>/webhook` with Telegram's `setWebhook` method, supplying `secret_token` equal to `TELEGRAM_WEBHOOK_SECRET`. Check `/health` and Telegram `getWebhookInfo` after deploying.

**Backend discrepancy:** `nextxus-sim/roger-sim.html` references `https://roger-sim-api.onorender.com/chat`, which does not resolve. The live `roger-sim-api.onrender.com` backend implements `POST /v1/chat/completions` (not `/chat`) and requires `BRIDGE_TOKEN`. This bridge uses that verified endpoint and parses `choices[0].message.content`. The `session_id` is sent as metadata, but the present backend ignores it, so conversation history is not retained.

For local tests: `python -m pytest test_main.py -x -q`.
