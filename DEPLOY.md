# Deploy linuxprivesctoday.site

Below is the **exact** list of actions you need to take. I've done everything I can locally; these are the steps that require your accounts/keys/DNS.

Estimated time: ~10 minutes.

---

## 1) Push to GitHub

```bash
cd "/Users/martin/Library/Mobile Documents/com~apple~CloudDocs/proj/random/linuxprivescweb"
git init -b main
git add .
git commit -m "init: linuxprivesctoday"
gh repo create linuxprivesctoday --public --source=. --remote=origin --push
```

(Or create the repo in the GitHub UI and `git remote add origin … && git push -u origin main`.)

## 2) Add the OpenRouter key as a repo secret

GitHub UI → repo → **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `OPENROUTER_API_KEY`
- Value: your key from <https://openrouter.ai/keys>

Optional: in **Variables** (not secrets) tab, set `OPENROUTER_MODEL` to override the default
(`anthropic/claude-haiku-4-5`). Other choices: `google/gemini-2.5-flash-lite` (~20× cheaper),
`openai/gpt-4o-mini`, `meta-llama/llama-3.3-70b-instruct`.

## 3) Trigger the first run

GitHub UI → **Actions → update-data → Run workflow**.

Wait ~1 min. It'll commit `public/data.json` populated with classifications.

## 4) Host on Cloudflare Pages (free, easiest for the apex domain)

1. <https://dash.cloudflare.com/> → **Workers & Pages → Create → Pages → Connect to Git**.
2. Pick the `linuxprivesctoday` repo.
3. Build settings:
   - Framework preset: **None**
   - Build command: *(leave empty)*
   - Build output directory: `public`
4. **Save and Deploy**. You'll get a `*.pages.dev` URL — confirm the site loads.

## 5) Point linuxprivesctoday.site at Cloudflare Pages

You said you're registering the domain "right now". Two paths:

### Path A — register via Cloudflare Registrar (recommended, simplest)
- Cloudflare → **Domains → Register Domains** → `linuxprivesctoday.site`.
- Once registered, in the Pages project → **Custom domains → Set up a custom domain** → `linuxprivesctoday.site` and `www.linuxprivesctoday.site`. Cloudflare wires DNS for you.

### Path B — registered elsewhere (Namecheap/Porkbun/etc.)
1. In your registrar, change nameservers to the two Cloudflare gives you (Cloudflare → **Add a site**).
2. Once Cloudflare shows the site as Active, in the Pages project add the custom domain — it'll add the right CNAMEs/records automatically.

## 6) Verify

- <https://linuxprivesctoday.site> shows a status banner.
- The hourly cron (`.github/workflows/update.yml`) keeps `data.json` fresh; Cloudflare Pages auto-redeploys on every push to `main`.

---

## Cost expectations

OpenRouter classification cost with the chosen `claude-haiku-4-5` and a 3-hourly cron: roughly **$0.30–1/month**. Each run classifies only *new* HN stories matching the keyword queries (typically 0–10/run), with ~300-token prompts. Switching to `gemini-2.5-flash-lite` would drop this to <$0.05/month.

GitHub Actions: free tier covers this easily (≈30s/run, 8 runs/day).

Cloudflare Pages: free.

## Tweaking

- **Add more search queries**: edit `QUERIES` in `scripts/update.py`.
- **Change retention/lookback**: `LOOKBACK_DAYS` and `RETENTION_DAYS` in the same file.
- **Change confidence threshold for the front page**: `MIN_CONFIDENCE` in `public/script.js`.
- **Extra sources**: the script is structured around `fetch_hn()`. Add a `fetch_oss_sec()` etc. and union the lists before classification.

## Optional: local end-to-end test before pushing

```bash
source .venv/bin/activate    # already created
export OPENROUTER_API_KEY=sk-or-...
python scripts/update.py
python -m http.server -d public 8000
# open http://localhost:8000
```
