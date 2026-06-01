from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
PBKDF2_ITERATIONS = 180_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> None:
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Enter a valid email address.")


def load_users() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]", encoding="utf-8")
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))


def save_users(users: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return salt, digest


def create_user(
    username: str = "",
    password: str = "",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
) -> dict:
    normalized_email = normalize_email(email)
    normalized_username = normalize_username(normalized_email or username)
    if not normalized_username:
        raise ValueError("Email is required.")
    if normalized_email:
        validate_email(normalized_email)
    if not first_name.strip():
        raise ValueError("First name is required.")
    if not last_name.strip():
        raise ValueError("Last name is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    users = load_users()
    if any(user.get("username") == normalized_username or user.get("email") == normalized_email for user in users):
        raise ValueError("An account with that email already exists.")

    salt, password_hash = hash_password(password)
    user = {
        "id": secrets.token_hex(12),
        "username": normalized_username,
        "email": normalized_email or normalized_username,
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "profile": default_profile(),
        "salt": salt,
        "password_hash": password_hash,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    users.append(user)
    save_users(users)
    return public_user(user)


def authenticate_user(username: str, password: str) -> dict | None:
    normalized_username = normalize_username(username)
    for user in load_users():
        if user.get("username") != normalized_username and user.get("email") != normalized_username:
            continue
        _, candidate_hash = hash_password(password, user.get("salt", ""))
        if hmac.compare_digest(candidate_hash, user.get("password_hash", "")):
            return public_user(user)
    return None


def update_user_profile(username: str, **profile_fields) -> dict:
    normalized_username = normalize_username(username)
    users = load_users()
    updated_user = None
    for user in users:
        if user.get("username") != normalized_username:
            continue
        profile = {**default_profile(), **user.get("profile", {})}
        for key, value in profile_fields.items():
            if key in {"first_name", "last_name", "email"}:
                if key == "email":
                    normalized_email = normalize_email(str(value))
                    validate_email(normalized_email)
                    user["email"] = normalized_email
                    user["username"] = normalized_email
                else:
                    user[key] = str(value).strip()
            elif key in profile:
                profile[key] = value
        user["profile"] = profile
        user["updated_at"] = utc_now()
        updated_user = user
        break

    if updated_user is None:
        raise ValueError("User not found.")
    save_users(users)
    return public_user(updated_user)


def default_profile() -> dict:
    return {
        "target_role_family": "",
        "target_seniority": "",
        "preferred_locations": "",
        "work_authorization": "",
        "needs_sponsorship": False,
        "linkedin_url": "",
        "github_url": "",
        "portfolio_url": "",
        "current_title": "",
        "years_experience": 0,
        "open_to_relocation": False,
    }


def public_user(user: dict) -> dict:
    return {
        "id": user.get("id", ""),
        "username": user.get("username", ""),
        "email": user.get("email", user.get("username", "")),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "profile": {**default_profile(), **user.get("profile", {})},
        "created_at": user.get("created_at", ""),
    }
