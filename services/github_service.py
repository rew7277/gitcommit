import httpx
import hashlib
import hmac
from config import settings

GITHUB_OAUTH_URL   = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL   = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE    = "https://api.github.com"


def get_oauth_url(state: str) -> str:
    return (
        f"{GITHUB_OAUTH_URL}"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=repo,read:user"
        f"&state={state}"
    )


async def exchange_code_for_token(code: str) -> str | None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        data = r.json()
        return data.get("access_token")


async def get_github_user(token: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GITHUB_API_BASE}/user",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        )
        return r.json()


async def get_user_repos(token: str) -> list[dict]:
    repos = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(
                f"{GITHUB_API_BASE}/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
                headers={"Authorization": f"token {token}"},
            )
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return repos


async def get_pr_diff(token: str, full_name: str, pr_number: int) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GITHUB_API_BASE}/repos/{full_name}/pulls/{pr_number}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3.diff",
            },
            follow_redirects=True,
        )
        return r.text


async def post_pr_comment(token: str, full_name: str, pr_number: int, body: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GITHUB_API_BASE}/repos/{full_name}/issues/{pr_number}/comments",
            json={"body": body},
            headers={"Authorization": f"token {token}"},
        )
        return r.status_code == 201


async def create_webhook(token: str, full_name: str, webhook_url: str) -> int | None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GITHUB_API_BASE}/repos/{full_name}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["pull_request", "push"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": settings.GITHUB_WEBHOOK_SECRET,
                    "insecure_ssl": "0",
                },
            },
            headers={"Authorization": f"token {token}"},
        )
        if r.status_code == 201:
            return r.json().get("id")
        return None


async def delete_webhook(token: str, full_name: str, webhook_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{GITHUB_API_BASE}/repos/{full_name}/hooks/{webhook_id}",
            headers={"Authorization": f"token {token}"},
        )
        return r.status_code == 204


async def commit_file_to_branch(
    token: str,
    full_name: str,
    branch: str,
    file_path: str,
    content: str,
    commit_message: str,
) -> bool:
    """Create or update a file on a branch. Creates the branch if it doesn't exist."""
    import base64

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"token {token}"}

        # Get default branch SHA to create new branch from
        repo_r = await client.get(f"{GITHUB_API_BASE}/repos/{full_name}", headers=headers)
        default_branch = repo_r.json().get("default_branch", "main")
        ref_r = await client.get(
            f"{GITHUB_API_BASE}/repos/{full_name}/git/ref/heads/{default_branch}",
            headers=headers,
        )
        if ref_r.status_code != 200:
            return False
        sha = ref_r.json()["object"]["sha"]

        # Create branch if it doesn't exist
        branch_r = await client.get(
            f"{GITHUB_API_BASE}/repos/{full_name}/git/ref/heads/{branch}",
            headers=headers,
        )
        if branch_r.status_code == 404:
            await client.post(
                f"{GITHUB_API_BASE}/repos/{full_name}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": sha},
                headers=headers,
            )

        # Get existing file SHA if it exists
        existing_sha = None
        file_r = await client.get(
            f"{GITHUB_API_BASE}/repos/{full_name}/contents/{file_path}",
            params={"ref": branch},
            headers=headers,
        )
        if file_r.status_code == 200:
            existing_sha = file_r.json().get("sha")

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        put_r = await client.put(
            f"{GITHUB_API_BASE}/repos/{full_name}/contents/{file_path}",
            json=payload,
            headers=headers,
        )
        return put_r.status_code in (200, 201)


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
