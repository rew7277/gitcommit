import json
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from database import get_db, Repository, Review, User
from services.github_service import (
    verify_webhook_signature, get_pr_diff, post_pr_comment,
    commit_file_to_branch,
)
from services.ai_service import generate_review, format_pr_comment
from config import settings
from datetime import datetime

router = APIRouter(prefix="/webhook", tags=["webhook"])


async def process_pull_request(
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    pr_url: str,
    pr_author: str,
    review_id: int,
):
    """Background task: fetch diff → AI review → post comment → optionally commit docs."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            return

        repo = db.query(Repository).filter(Repository.id == review.repo_id).first()
        if not repo:
            return

        user = db.query(User).filter(User.id == repo.user_id).first()
        if not user:
            return

        review.status = "processing"
        db.commit()

        # 1. Fetch diff
        diff = await get_pr_diff(user.access_token, repo_full_name, pr_number)
        review.diff_size = len(diff)

        # 2. AI review
        result = await generate_review(diff)

        review.raw_review      = result["raw_review"]
        review.summary         = result["summary"]
        review.api_changes     = result["api_changes"]
        review.breaking        = result["breaking"]
        review.security_issues = result["security"]
        review.meta            = {"risk": result["risk"]}
        review.status          = "done"
        review.updated_at      = datetime.utcnow()
        db.commit()

        # 3. Post PR comment
        comment_body = format_pr_comment(result, repo.name, pr_number)
        await post_pr_comment(user.access_token, repo_full_name, pr_number, comment_body)

        # 4. Optionally commit docs
        if settings.AUTO_COMMIT_DOCS:
            doc_content = f"# API Review — PR #{pr_number}: {pr_title}\n\n{result['raw_review']}"
            file_path   = f"docs/reviews/pr-{pr_number}.md"
            committed   = await commit_file_to_branch(
                token=user.access_token,
                full_name=repo_full_name,
                branch=settings.DOCS_BRANCH,
                file_path=file_path,
                content=doc_content,
                commit_message=f"docs: AI review for PR #{pr_number} [skip ci]",
            )
            review.doc_committed = committed
            review.doc_branch    = settings.DOCS_BRANCH if committed else None
            db.commit()

    except Exception as e:
        db = SessionLocal()
        review = db.query(Review).filter(Review.id == review_id).first()
        if review:
            review.status   = "error"
            review.meta     = {"error": str(e)}
            review.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    payload_bytes = await request.body()
    signature     = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(payload_bytes, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event   = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(payload_bytes)

    # Only handle PR opened/synchronize events
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    pr          = payload["pull_request"]
    repo_data   = payload["repository"]
    full_name   = repo_data["full_name"]
    pr_number   = pr["number"]
    pr_title    = pr["title"]
    pr_url      = pr["html_url"]
    pr_author   = pr["user"]["login"]
    gh_repo_id  = repo_data["id"]

    # Find the repository in our DB
    repo = db.query(Repository).filter(
        Repository.github_id == gh_repo_id,
        Repository.active == True,
    ).first()

    if not repo:
        return {"status": "ignored", "reason": "repo not registered"}

    # Avoid duplicate reviews for same PR+commit
    existing = db.query(Review).filter(
        Review.repo_id    == repo.id,
        Review.pr_number  == pr_number,
        Review.status.in_(["pending", "processing", "done"]),
    ).first()

    if existing and action == "opened":
        return {"status": "duplicate", "review_id": existing.id}

    # Create review record
    review = Review(
        repo_id    = repo.id,
        pr_number  = pr_number,
        pr_title   = pr_title,
        pr_url     = pr_url,
        pr_author  = pr_author,
        status     = "pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    background_tasks.add_task(
        process_pull_request,
        repo_full_name=full_name,
        pr_number=pr_number,
        pr_title=pr_title,
        pr_url=pr_url,
        pr_author=pr_author,
        review_id=review.id,
    )

    return {"status": "queued", "review_id": review.id}
