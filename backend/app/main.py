# app/main.py - FIXED VERSION
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from sqlalchemy import text
from app.database.database import engine, Base
from app.routes import triage, advice, referrals, rx_draft, auth, patient_profile
from app.services.auth_service import verify_token
from dotenv import load_dotenv

load_dotenv()

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"❌ Error creating tables: {e}")

app = FastAPI(title="AI Doctor Backend (OpenRouter)")

# EHR Configuration
EHR_ENABLED = True
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")

print(f" EHR Integration: {'ENABLED' if EHR_ENABLED else 'DISABLED'}")
print(f" FHIR Server: {FHIR_BASE_URL}")

# Comma-separated list of allowed browser origins. Defaults to local dev only:
# production must set ALLOWED_ORIGINS explicitly. Native iOS clients do not send
# an Origin header, so CORS does not apply to them -- this is for web callers.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8081").split(",") if o.strip()
]

# "*" and allow_credentials=True is rejected by browsers, and echoing arbitrary
# origins back with credentials enabled would let any site make authenticated
# calls on a logged-in user's behalf. Only send credentials to a known origin list.
ALLOW_CREDENTIALS = "*" not in ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    # Public endpoints, matched exactly. "/" MUST be matched exactly and never
    # used as a prefix: every path starts with "/", so a prefix test against it
    # makes this entire middleware a no-op and leaves every route unauthenticated.
    public_exact = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    # Public endpoints, matched by prefix (these have sub-paths).
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/patient/discover",
        # "/patient/profile",
        # "/patient/medications",
        # "/ehr-advice",
        "/triage",
        # "/analytics",
        "/metrics",
    )

    path = request.url.path
    if path in public_exact or path.startswith(public_prefixes):
        return await call_next(request)

    # NOTE: raising HTTPException from inside an @app.middleware("http") function
    # does NOT produce a 401 -- Starlette's BaseHTTPMiddleware runs outside the
    # exception handlers that translate HTTPException into a response, so it
    # surfaces as an unhandled 500. Return a JSONResponse explicitly instead.
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.replace("Bearer ", "")
    payload = verify_token(token)

    if not payload:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"🔐 Auth: Valid token for user {payload.get('sub')} - {request.url.path}")

    response = await call_next(request)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(">>", request.method, request.url.path)
    try:
        resp = await call_next(request)
        print("<<", resp.status_code, request.url.path)
        return resp
    except Exception as e:
        print("!!", request.url.path, repr(e))
        raise


# Add to main.py for debugging
@app.middleware("http")
async def debug_auth(request: Request, call_next):
    auth_header = request.headers.get("Authorization")
    if auth_header:
        print(f"🔐 Token present for: {request.url.path}")
    else:
        print(f"🔓 No token for: {request.url.path}")

    response = await call_next(request)
    return response


# Include base routers
app.include_router(auth.router)
app.include_router(triage.router)
app.include_router(advice.router)
app.include_router(referrals.router)
app.include_router(rx_draft.router)

# Conditionally include EHR routers
if EHR_ENABLED:
    try:
        from app.routes.patient_profile import router as patient_profile_router
        from app.ehr.ehr_advice import router as ehr_advice_router

        app.include_router(ehr_advice_router)
        app.include_router(patient_profile_router)
        print("✅ EHR routes registered: /ehr-advice, /patient/profile")
    except ImportError as e:
        print(f"Failed to import EHR: {e}")

analytics_succeed = False
try:
    from app.routes.analytics import router as analytics_router

    app.include_router(analytics_router)
    print("✅ Analytics routes registered")
    analytics_succeed = True
except ImportError as e:
    print(f"Analytics routes not available: {e}")

try:
    from app.routes.reminders import router as reminders_router

    app.include_router(reminders_router)
    print("✅ Reminder routes registered")
except ImportError as e:
    print(f"Reminder routes not available: {e}")

try:
    from app.routes.metrics import router as metrics_router

    app.include_router(metrics_router)
    print("✅ Metrics routes registered")
except ImportError as e:
    print(f"Metrics routes not available: {e}")


@app.get("/")
async def root():
    ehr_status = "enabled" if EHR_ENABLED else "disabled"
    return {
        "message": "AI Doctor Chatbot API is running!",
        "status": "healthy",
        "ehr_integration": ehr_status,
        "fhir_server": FHIR_BASE_URL if EHR_ENABLED else "none",
        "analytics": analytics_succeed if analytics_succeed else "none",
    }


@app.get("/health")
async def health():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            db_test = result.scalar()

        health_info = {
            "status": "healthy",
            "database": "connected",
            "service": "AI Doctor Chatbot API",
            "database_test": db_test,
            "ehr_integration": "enabled" if EHR_ENABLED else "disabled",
        }

        if EHR_ENABLED:
            health_info["fhir_server"] = FHIR_BASE_URL

        return health_info

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "ehr_integration": "enabled" if EHR_ENABLED else "disabled",
                "error": str(e),
            },
        )
