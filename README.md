# rzr-invest

React (Vite) app for rzr-investing, with a Flask backend under `backend/`.

## Development

```bash
npm install
npm run dev
```

The dev server proxies `/api` to the Flask backend on port 5001:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
FLASK_APP=app.py .venv/bin/flask run --port 5001
```

## Backend configuration

Set these in the backend's environment (shell, or the host's WSGI config):

| Variable | Used by | Notes |
| --- | --- | --- |
| `ALPACA_API_KEY` | stock price, insider screener | Alpaca **paper** account key. |
| `ALPACA_SECRET_KEY` | stock price, insider screener | Alpaca paper account secret. |
| `EDGAR_IDENTITY` | insider data, insider screener | `name email` string SEC EDGAR requires on every request. Defaults to a placeholder if unset. |

The insider screener (epic SCRUM-29) uses Alpaca for read-only market data
and paper-account context only; it never places orders, and the trading
client is pinned to Alpaca's paper environment.
