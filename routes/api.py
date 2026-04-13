from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Review, Repository
from routes.auth import get_current_user

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/reviews/{review_id}/status")
async def review_status(review_id: int, request: Request, db: Session = Depends(get_db)):
    user   = get_current_user(request, db)
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404)
    return {
        "id":       review.id,
        "status":   review.status,
        "breaking": review.breaking,
        "security": review.security_issues,
        "risk":     review.meta.get("risk", "UNKNOWN") if review.meta else "UNKNOWN",
    }


@router.get("/repos/{repo_id}/reviews")
async def repo_reviews(repo_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.user_id == user.id).first()
    if not repo:
        raise HTTPException(status_code=404)
    reviews = db.query(Review).filter(Review.repo_id == repo_id)\
                .order_by(Review.created_at.desc()).limit(50).all()
    return [
        {
            "id":        r.id,
            "pr_number": r.pr_number,
            "pr_title":  r.pr_title,
            "status":    r.status,
            "breaking":  r.breaking,
            "security":  r.security_issues,
            "risk":      r.meta.get("risk") if r.meta else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in reviews
    ]
