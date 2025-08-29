# security.py
import os, time, re, hmac
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from starlette.datastructures import MutableHeaders
from starlette.requests import Request

APP_ENV = os.getenv("APP_ENV", "development")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Tune these safely
MAX_UPLOAD_BYTES = 30 * 1024 * 1024   # 30 MB request cap
RATE_WINDOW_SECS = 60
RATE_MAX_REQUESTS = 90                # per IP per minute

# simple in-memory bucket {ip: [timestamps]}
_RATE_BUCKET = {}

# Allow your domain (edit 'yourdomain.com' once you point DNS)
SAFE_ORIGIN_RE = re.compile(r"^https://([a-z0-9-]+\.)*yourdomain\.com$", re.I)

def _set_security_headers(headers: MutableHeaders):
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "script-src 'self'; "
        "style-src 'self'; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if APP_ENV.lower() == "production":
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    return bool(SAFE_ORIGIN_RE.match(origin))

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1) Size cap (fast reject)
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_UPLOAD_BYTES:
            return PlainTextResponse("Payload too large", status_code=413)

        # 2) Per-IP rate limit
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _RATE_BUCKET.setdefault(ip, [])
        # drop old
        cutoff = now - RATE_WINDOW_SECS
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= RATE_MAX_REQUESTS:
            return PlainTextResponse("Too many requests", status_code=429)
        bucket.append(now)

        # 3) Continue
        response = await call_next(request)

        # 4) Security headers
        _set_security_headers(response.headers)

        # 5) Tight CORS
        origin = request.headers.get("origin")
        if origin and _origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "authorization,content-type,x-admin-secret"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        elif origin:
            response.headers["Access-Control-Allow-Origin"] = "null"

        return response
