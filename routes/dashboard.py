from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, Repository, Review
from routes.auth import get_current_user
from services.github_service import get_user_repos, create_webhook, delete_webhook
from config import settings

router     = APIRouter(tags=["dashboard"])
templates  = Jinja2Templates(directory="templates")


def require_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return user


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    repos = db.query(Repository).filter(
        Repository.user_id == user.id,
        Repository.active == True,
    ).all()

    stats = {
        "total_repos":    len(repos),
        "total_reviews":  db.query(Review).join(Repository).filter(Repository.user_id == user.id).count(),
        "breaking":       db.query(Review).join(Repository).filter(
                              Repository.user_id == user.id, Review.breaking == True).count(),
        "security":       db.query(Review).join(Repository).filter(
                              Repository.user_id == user.id, Review.security_issues == True).count(),
    }

    recent = (
        db.query(Review)
        .join(Repository)
        .filter(Repository.user_id == user.id)
        .order_by(Review.created_at.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user":    user,
        "repos":   repos,
        "stats":   stats,
        "recent":  recent,
    })


@router.get("/repos/connect", response_class=HTMLResponse)
async def connect_repos_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    gh_repos = await get_user_repos(user.access_token)
    connected_ids = {r.github_id for r in db.query(Repository).filter(
        Repository.user_id == user.id).all()}

    return templates.TemplateResponse("connect_repos.html", {
        "request":       request,
        "user":          user,
        "gh_repos":      gh_repos,
        "connected_ids": connected_ids,
    })


@router.post("/repos/connect")
async def connect_repo(
    request: Request,
    github_id: int   = Form(...),
    full_name: str   = Form(...),
    name: str        = Form(...),
    description: str = Form(""),
    private: bool    = Form(False),
    db: Session      = Depends(get_db),
):
    user = require_user(request, db)

    existing = db.query(Repository).filter(Repository.github_id == github_id).first()
    if existing:
        return RedirectResponse("/repos/connect?msg=already_connected", status_code=302)

    webhook_url = f"{settings.APP_URL}/webhook/github"
    webhook_id  = await create_webhook(user.access_token, full_name, webhook_url)

    repo = Repository(
        user_id     = user.id,
        github_id   = github_id,
        full_name   = full_name,
        name        = name,
        description = description,
        private     = private,
        webhook_id  = webhook_id,
        active      = True,
    )
    db.add(repo)
    db.commit()
    return RedirectResponse("/dashboard?msg=repo_connected", status_code=302)


@router.post("/repos/{repo_id}/disconnect")
async def disconnect_repo(repo_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.user_id == user.id).first()
    if not repo:
        raise HTTPException(status_code=404)

    if repo.webhook_id:
        await delete_webhook(user.access_token, repo.full_name, repo.webhook_id)

    db.delete(repo)
    db.commit()
    return RedirectResponse("/dashboard?msg=repo_disconnected", status_code=302)


@router.get("/reviews", response_class=HTMLResponse)
async def reviews_list(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    reviews = (
        db.query(Review)
        .join(Repository)
        .filter(Repository.user_id == user.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("reviews.html", {
        "request": request, "user": user, "reviews": reviews,
    })


@router.get("/reviews/{review_id}", response_class=HTMLResponse)
async def review_detail(review_id: int, request: Request, db: Session = Depends(get_db)):
    user   = require_user(request, db)
    review = db.query(Review).join(Repository).filter(
        Review.id == review_id, Repository.user_id == user.id).first()
    if not review:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("review_detail.html", {
        "request": request, "user": user, "review": review,
    })
