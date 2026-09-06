"""
Authentication helpers for Qgurukul (Flask + Supabase).

WHY THIS FILE EXISTS
--------------------
Keep login/session rules in one place so routes stay thin.
The app uses *Flask sessions* (a signed cookie) as the login token,
and *Supabase* as the source of truth for the user profile (name, plan, limits).

WHY NOT FULL SUPABASE AUTH (GoTrue) IN THIS PASS
------------------------------------------------
You already store profiles in a public `users` table and log people in with
Flask `session`. Switching to Supabase Auth (JWT + email confirmation) is
the right long-term move, but it would force every existing user to reset
a password and would take more than a 2-day ship.

This layer is the stepping stone:
  Browser  -->  Flask session cookie (who is logged in)
  Flask    -->  Supabase `users` row (profile + plan + rate limits)

NEVER put SUPABASE_KEY or GROQ_API_KEY in templates or client-side JS.
The anon/service key lives only in server env vars.
"""

from functools import wraps
from flask import session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash


def plan_from_user(user):
    """
    Map boolean flags on the users row to a single display name.

    Super Premium beats Premium beats Free.
    We read these from the DATABASE on the dashboard, not from the cookie,
    so an admin can upgrade someone in Supabase and they see it immediately.
    """
    if not user:
        return "Free"
    if user.get("is_super_premium"):
        return "Super Premium"
    if user.get("is_premium"):
        return "Premium"
    return "Free"


def login_user(user):
    """
    Store a minimal identity in the Flask session.

    Session fixation: we rotate the session first so an old anonymous cookie
    cannot be reused after login.
    We store email + display fields only — never passwords or API keys.
    """
    session.clear()
    session["user_email"] = user["email"]
    session["user_name"] = user.get("name") or ""
    session["user_premium"] = bool(user.get("is_premium"))
    session["user_super_premium"] = bool(user.get("is_super_premium"))
    session["user_role"] = user.get("role", "student")
    session["institute_name"] = user.get("institute_name", "")
    session["city"] = user.get("city", "")
    session["mobile"] = user.get("mobile", "")
    session.permanent = True  # uses PERMANENT_SESSION_LIFETIME from app.py


def logout_user():
    """Wipe the signed cookie. Next request is anonymous."""
    session.clear()


def current_email():
    """Email stored in the session, or None if logged out."""
    return session.get("user_email")


def is_logged_in():
    return bool(current_email())


def hash_password(plain_password):
    """
    One-way hash (pbkdf2 by default in Werkzeug).
    We never store or log the plain password.
    """
    return generate_password_hash(plain_password)


def password_matches(user, plain_password):
    """
    Legacy-safe check:
    - If the row has password_hash, the typed password MUST match.
    - If the row has no password (older signups), we accept email-only login
      so existing teachers are not locked out. Dashboard can later prompt them
      to set a password (not built in this pass).
    """
    stored = user.get("password_hash")
    if not stored:
        return True
    if not plain_password:
        return False
    return check_password_hash(stored, plain_password)


def safe_next_url(candidate, fallback_endpoint="dashboard"):
    """
    Prevent open-redirect attacks: only allow relative paths on this site
    (must start with a single slash, not //evil.com).
    """
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return url_for(fallback_endpoint)


def login_required(view_func):
    """
    Decorator for protected pages (dashboard, later: billing, history).

    If there is no session email, send the user to /login and remember
    the page they wanted (`?next=/dashboard`).
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapper
