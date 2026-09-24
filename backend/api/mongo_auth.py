"""
mongo_auth.py — FastAPI router for /api/auth
Ports the Node.js auth.js routes 1:1:
  POST /api/auth/register
  POST /api/auth/login
  GET  /api/auth/me

JWT format: HS256, payload {id: str(ObjectId)}, 30-day expiry.
Same secret as Node backend → existing frontend tokens stay valid.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import bcrypt
from jose import JWTError, jwt
from beanie import PydanticObjectId

from db.mongo_models import User, Source

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Security helpers ────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET", "feedtoread_secret_key_2026_broadsheet")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

bearer_scheme = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _generate_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"id": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """Dependency: validate Bearer token and return the User document."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authorized, no token provided")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authorized, token failed")
    except JWTError:
        raise HTTPException(status_code=401, detail="Not authorized, token failed")

    user = await User.get(PydanticObjectId(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Not authorized, user not found")
    return user


def _user_response(user: User, token: str) -> dict:
    return {
        "_id": str(user.id),
        "name": user.name,
        "email": user.email,
        "token": token,
        "last_checked_at": user.last_checked_at.isoformat() + "Z" if user.last_checked_at else None,
        "created_at": user.created_at.isoformat() + "Z" if user.created_at else None,
    }


# ── Default sources seeded on registration ──────────────────────────────────

DEFAULT_SEEDS = [
    {"name": "The Hindu",        "type": "BLOG"},
    {"name": "Times of India",   "type": "BLOG"},
    {"name": "Daily Thanthi",    "type": "NEWSLETTER"},
    {"name": "The Verge",        "type": "BLOG"},
]


# ── Request bodies ───────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    name: str
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    if not body.name or not body.email or not body.password:
        raise HTTPException(status_code=400, detail="Name, email, and password are required.")

    email = body.email.lower().strip()

    existing = await User.find_one(User.email == email)
    if existing:
        raise HTTPException(status_code=400, detail="A subscriber with this email already exists.")

    password_hash = _hash_password(body.password)
    now = datetime.utcnow()

    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=password_hash,
        last_checked_at=now,
        created_at=now,
    )
    await user.insert()

    # Seed default sources — failure is non-fatal (matches Node behaviour)
    try:
        seeds = [
            Source(
                userId=user.id,
                sourceName=s["name"],
                sourceType=s["type"],
                isActive=True,
            )
            for s in DEFAULT_SEEDS
        ]
        for seed in seeds:
            await seed.insert()
    except Exception as e:
        print(f"[auth] Failed to seed default sources on registration: {e}")

    token = _generate_token(str(user.id))
    return _user_response(user, token)


import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from api.utils_extractor import trigger_extractors

@router.post("/login", status_code=200)
async def login(body: LoginBody, background_tasks: BackgroundTasks):
    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    email = body.email.lower().strip()
    user = await User.find_one(User.email == email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid subscriber credentials.")

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid subscriber credentials.")

    token = _generate_token(str(user.id))
    
    # Auto-trigger youtube extractor if user has wired YOUTUBE sources
    has_youtube = await Source.find_one(
        Source.userId == user.id,
        Source.sourceType == "YOUTUBE",
        Source.isActive == True
    )
    if has_youtube:
        background_tasks.add_task(trigger_extractors)
        
    return _user_response(user, token)


@router.get("/me", status_code=200)
async def me(current_user: User = Depends(get_current_user)):
    # Return user without password_hash (mirrors .select('-password_hash'))
    return {
        "_id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "last_checked_at": current_user.last_checked_at.isoformat() + "Z" if current_user.last_checked_at else None,
        "created_at": current_user.created_at.isoformat() + "Z" if current_user.created_at else None,
    }
