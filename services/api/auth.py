"""
JWT Authenticatie - Login, token generatie en role-based access.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import config
from shared.database import get_db
from shared.models.user import User, UserRole

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = config.security.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.security.session_timeout_minutes

# Bearer token extractor
security = HTTPBearer()


# --- Pydantic Models ---

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class CurrentUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: str


# --- Helpers ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user_id: str, role: str) -> tuple[str, datetime]:
    """Maak een JWT token aan. Retourneert (token, expiry)."""
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expires,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expires


# --- Dependencies ---

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    FastAPI dependency: haal de ingelogde gebruiker op uit het JWT token.
    Gebruik als: current_user: CurrentUser = Depends(get_current_user)
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Ongeldig token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Ongeldig of verlopen token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Gebruiker niet gevonden of inactief")

    return CurrentUser(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
    )


def require_role(*roles: str):
    """
    Dependency factory: beperk toegang tot bepaalde rollen.

    Gebruik:
        @app.get("/admin", dependencies=[Depends(require_role("beheerder"))])
    """
    async def check_role(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Geen toegang. Vereiste rol: {', '.join(roles)}"
            )
        return current_user
    return check_role
