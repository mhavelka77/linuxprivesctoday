# linuxprivesctoday

A static site that answers one question: **was a new Linux privesc dropped today?**

Hourly, a GitHub Action:
1. Searches Hacker News (Algolia API) for stories with privesc-relevant keywords over the last 14 days.
2. Sends each new story title + URL to an OpenRouter LLM that classifies it.
3. Merges results into `public/data.json` and commits if changed.

The frontend is plain HTML/CSS/JS — it just fetches `data.json` and renders.

## Local test

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...
python scripts/update.py
# then serve public/
python -m http.server -d public 8000
```

## Configuration

| Env var | Default | Notes |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | (required) | Your key from openrouter.ai |
| `OPENROUTER_MODEL` | `anthropic/claude-haiku-4-5` | Any chat model on OpenRouter that supports `response_format` |

## Deployment

See `DEPLOY.md`.
