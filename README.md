# ⬡ AI API Reviewer

> Connect your GitHub repo → every PR automatically gets an AI code review, breaking-change detection, security analysis, and optional doc commits — posted directly as a PR comment.

---

## Features

- **AI Code Review** — structured review posted as a PR comment (summary, API changes, breaking changes, security issues, suggestions)
- **Risk Scoring** — LOW / MEDIUM / HIGH per PR
- **Auto Docs Commit** — optionally commits AI-generated review docs to a configurable branch
- **GitHub OAuth** — one-click login, webhook auto-registration per repo
- **Dark Dashboard** — view all reviews, filter by repo, inspect full AI output

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI |
| Database | PostgreSQL (Railway) / SQLite (local dev) |
| AI | Anthropic Claude or OpenAI GPT-4 |
| Auth | GitHub OAuth App |
| Webhooks | GitHub Webhooks (HMAC-verified) |
| Hosting | Railway |
| CI/CD | GitHub Actions → Railway CLI |

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/ai-api-reviewer.git
cd ai-api-reviewer
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a GitHub OAuth App

1. Go to **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App**
2. Set:
   - **Homepage URL:** `http://localhost:8000`
   - **Callback URL:** `http://localhost:8000/auth/callback`
3. Copy the **Client ID** and **Client Secret**

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=sqlite:///./dev.db        # SQLite for local dev
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_WEBHOOK_SECRET=any_random_string
SECRET_KEY=any_random_string
AI_PROVIDER=anthropic                  # or openai
ANTHROPIC_API_KEY=sk-ant-...
APP_URL=http://localhost:8000
```

> Generate random secrets: `python -c "import secrets; print(secrets.token_hex(32))"`

### 4. Run

```bash
uvicorn app:app --reload --port 8000
```

Open `http://localhost:8000` → sign in with GitHub → connect a repo.

> **Note:** For webhooks to work locally, use [ngrok](https://ngrok.com):
> ```bash
> ngrok http 8000
> ```
> Then update `APP_URL` in `.env` to your ngrok URL and update the GitHub OAuth App callback URL.

---

## Deploy to Railway

### Step 1 — Push to GitHub

```bash
git add .
git commit -m "initial commit"
git push origin main
```

### Step 2 — Create Railway project

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select your repo
3. Railway auto-detects the `railway.toml` and starts the build

### Step 3 — Add PostgreSQL

In Railway dashboard:
- Click **+ New** → **Database** → **PostgreSQL**
- Railway automatically sets `DATABASE_URL` in your service environment

### Step 4 — Set environment variables

In Railway → your service → **Variables**, add:

```
GITHUB_CLIENT_ID          = your_github_client_id
GITHUB_CLIENT_SECRET      = your_github_client_secret
GITHUB_WEBHOOK_SECRET     = your_random_secret
SECRET_KEY                = your_random_secret
AI_PROVIDER               = anthropic
ANTHROPIC_API_KEY         = sk-ant-...
APP_URL                   = https://your-app.railway.app
AUTO_COMMIT_DOCS          = false
DOCS_BRANCH               = ai-docs
```

### Step 5 — Update GitHub OAuth App

Go back to your GitHub OAuth App settings and update:
- **Homepage URL:** `https://your-app.railway.app`
- **Callback URL:** `https://your-app.railway.app/auth/callback`

### Step 6 — Set up CI/CD (auto-deploy on push)

1. In Railway → your service → **Settings → Generate Token** → copy the token
2. In your GitHub repo → **Settings → Secrets → Actions** → add:
   - Name: `RAILWAY_TOKEN`
   - Value: the token you copied

Now every push to `main` runs tests → deploys to Railway automatically.

---

## How It Works

```
Developer opens/updates a PR
           ↓
GitHub sends webhook → POST /webhook/github
           ↓
Signature verified (HMAC SHA-256)
           ↓
Background task: fetch diff from GitHub API
           ↓
Diff chunked if >12,000 chars
           ↓
AI generates structured review (summary, API changes,
breaking changes, security, suggestions, risk score)
           ↓
Review posted as PR comment
           ↓
(If AUTO_COMMIT_DOCS=true) docs committed to DOCS_BRANCH
           ↓
Review saved to DB → visible in dashboard
```

---

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✓ | — | PostgreSQL or SQLite URL |
| `GITHUB_CLIENT_ID` | ✓ | — | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | ✓ | — | GitHub OAuth App client secret |
| `GITHUB_WEBHOOK_SECRET` | ✓ | — | HMAC secret for webhook verification |
| `SECRET_KEY` | ✓ | — | Session cookie signing key |
| `AI_PROVIDER` | | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | if anthropic | — | Claude API key |
| `OPENAI_API_KEY` | if openai | — | OpenAI API key |
| `APP_URL` | ✓ | — | Public URL of your app (no trailing slash) |
| `AUTO_COMMIT_DOCS` | | `false` | Auto-commit review docs to `DOCS_BRANCH` |
| `DOCS_BRANCH` | | `ai-docs` | Branch to commit generated docs to |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Landing / login page |
| `GET` | `/auth/github` | Start GitHub OAuth |
| `GET` | `/auth/callback` | OAuth callback |
| `GET` | `/auth/logout` | Sign out |
| `POST` | `/webhook/github` | GitHub webhook receiver |
| `GET` | `/dashboard` | Main dashboard |
| `GET` | `/repos/connect` | Browse & connect repos |
| `POST` | `/repos/connect` | Connect a repo + install webhook |
| `POST` | `/repos/{id}/disconnect` | Remove repo + delete webhook |
| `GET` | `/reviews` | All reviews list |
| `GET` | `/reviews/{id}` | Review detail with full AI output |
| `GET` | `/api/reviews/{id}/status` | Poll review status (JSON) |
| `GET` | `/api/repos/{id}/reviews` | Repo review history (JSON) |
| `GET` | `/api/docs` | Swagger UI |
| `GET` | `/health` | Health check |

---

## Project Structure

```
ai-api-reviewer/
├── app.py                    # FastAPI entry point
├── config.py                 # Pydantic settings
├── database.py               # SQLAlchemy models (User, Repository, Review)
├── requirements.txt
├── railway.toml              # Railway deployment config
├── .env.example
├── .gitignore
├── routes/
│   ├── auth.py               # GitHub OAuth
│   ├── webhooks.py           # Webhook handler + background AI task
│   ├── dashboard.py          # UI routes
│   └── api.py                # JSON API endpoints
├── services/
│   ├── github_service.py     # GitHub API client (OAuth, diff, comments, webhooks)
│   └── ai_service.py         # AI review engine (Anthropic/OpenAI, chunking)
├── templates/
│   ├── base.html             # Dark layout with sidebar
│   ├── login.html
│   ├── dashboard.html
│   ├── connect_repos.html
│   ├── reviews.html
│   └── review_detail.html
├── static/
│   └── style.css
└── .github/
    └── workflows/
        └── deploy.yml        # Test + deploy to Railway on push to main
```

---

## Troubleshooting

**Webhook not triggering?**
- Confirm `APP_URL` is publicly accessible (use ngrok locally)
- Check webhook delivery in GitHub → repo → Settings → Webhooks → Recent Deliveries
- Ensure `GITHUB_WEBHOOK_SECRET` matches in both GitHub and your env

**Review stuck at "processing"?**
- Check Railway logs for AI API errors
- Verify your `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is valid
- Large diffs (>50k chars) may timeout — the chunker handles up to ~12k chars per chunk

**OAuth callback error?**
- Confirm the callback URL in GitHub OAuth App exactly matches `APP_URL/auth/callback`
- For Railway, use `https://` not `http://`

---

## License

MIT
