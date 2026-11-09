"""Browser-based Google sign-in for the hosted app (OAuth authorization code + PKCE).

Local mode keeps using the desktop flow in src/tools/google_auth.py. Tokens from
this flow stay in process memory and are never written to disk, so a server
restart signs everyone out.
"""
import base64
import datetime as dt
import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from google.oauth2.credentials import Credentials

from src.config import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
)

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Google lets users untick individual permissions, so all three are checked below.
REQUIRED_API_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
SCOPES = ["openid", "email", *REQUIRED_API_SCOPES]

_PENDING_TTL_SECONDS = 600
_REQUEST_TIMEOUT_SECONDS = 15

_lock = threading.Lock()
_pending: dict[str, tuple[str, str, float]] = {}  # state -> (visitor, verifier, expiry)


@dataclass
class GoogleAccount:
    email: str
    credentials: Credentials


class SignInError(Exception):
    """`reason` is a short code the frontend turns into a message."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def authorization_url(visitor: str) -> str:
    """Start sign-in, binding the attempt to this visitor's browser session."""
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    now = time.time()
    with _lock:
        for key in [k for k, (_, _, expiry) in _pending.items() if expiry < now]:
            del _pending[key]
        _pending[state] = (visitor, verifier, now + _PENDING_TTL_SECONDS)
    query = urlencode({
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",  # a refresh token keeps sessions alive past one hour
        "prompt": "consent",
    })
    return f"{AUTH_URL}?{query}"


def complete_sign_in(state: str, code: str, visitor: str) -> GoogleAccount:
    with _lock:
        pending = _pending.pop(state, None)
    if pending is None or pending[0] != visitor or pending[2] < time.time():
        raise SignInError("failed")

    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "code": code,
                "code_verifier": pending[1],
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        token = response.json()

        granted = token.get("scope", "").split()
        if any(scope not in granted for scope in REQUIRED_API_SCOPES):
            _revoke(token.get("refresh_token") or token["access_token"])
            raise SignInError("permissions")

        profile = httpx.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        profile.raise_for_status()
        email = profile.json()["email"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # Log only the exception type: these payloads can carry tokens.
        logger.warning("Google sign-in failed: %s", type(exc).__name__)
        raise SignInError("failed") from None

    # google-auth compares expiry against naive UTC datetimes.
    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    credentials = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=GOOGLE_OAUTH_CLIENT_ID,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=granted,
        expiry=now_utc + dt.timedelta(seconds=int(token.get("expires_in", 3600))),
    )
    return GoogleAccount(email=email, credentials=credentials)


def _revoke(token: str) -> None:
    try:
        httpx.post(REVOKE_URL, data={"token": token}, timeout=_REQUEST_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("Google token revocation failed: %s", type(exc).__name__)


def revoke(account: GoogleAccount) -> None:
    """Best effort: signing out here should also cancel the app's Google access."""
    _revoke(account.credentials.refresh_token or account.credentials.token)
