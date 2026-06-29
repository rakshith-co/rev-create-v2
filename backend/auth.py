import hashlib
import logging
from datetime import datetime, timezone
from pydantic import BaseModel

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

import repos.tokens as tokens_repo

logger = logging.getLogger("revCreate.auth")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthUser(BaseModel):
    org_name: str
    name: str | None = None


class AuthContext(BaseModel):
    user: AuthUser
    is_admin: bool
    client: str | None


def require_auth(require_client: bool = True):
    async def auth_dependency(
        api_key: str = Security(_api_key_header),
    ) -> AuthContext:
        if not api_key:
            raise HTTPException(status_code=401, detail="X-API-Key header required")

        token_hash = hash_token(api_key)
        doc = await tokens_repo.get_by_hash(token_hash)
        if not doc:
            raise HTTPException(status_code=401, detail="Invalid or inactive API key")

        org_name = doc.get("company_name", "unknown")
        is_admin = (org_name == "revspot")

        try:
            await tokens_repo.update_last_used(
                doc["_id"],
                datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.warning(f"Failed to update token last_used_at: {e}")

        return AuthContext(
            user=AuthUser(org_name=org_name, name=doc.get("name")),
            is_admin=is_admin,
            client=org_name if require_client else None,
        )

    return auth_dependency
