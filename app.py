from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
from database import init_db
from config import settings
from routes import auth, webhooks, dashboard, api


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI API Reviewer",
    description="Automated API documentation and code review powered by AI",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="ai_reviewer_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
    https_only=not settings.APP_URL.startswith("http://localhost"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(dashboard.router)
app.include_router(api.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
