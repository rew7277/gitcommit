import secrets
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db, User
from services.github_service import get_oauth_url, exchange_code_for_token, get_github_user
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
async def github_login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(get_oauth_url(state))


@router.get("/callback")
async def github_callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    if state != request.session.get("oauth_state"):
        return RedirectResponse("/?error=invalid_state")

    token = await exchange_code_for_token(code)
    if not token:
        return RedirectResponse("/?error=token_exchange_failed")

    gh_user = await get_github_user(token)
    if "id" not in gh_user:
        return RedirectResponse("/?error=user_fetch_failed")

    # Upsert user
    user = db.query(User).filter(User.github_id == gh_user["id"]).first()
    if not user:
        user = User(
            github_id=gh_user["id"],
            username=gh_user.get("login", ""),
            avatar_url=gh_user.get("avatar_url", ""),
            access_token=token,
        )
        db.add(user)
    else:
        user.access_token = token
        user.avatar_url = gh_user.get("avatar_url", user.avatar_url)
    db.commit()

    request.session["user_id"] = user.id
    request.session.pop("oauth_state", None)
    return RedirectResponse("/dashboard")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).first()
