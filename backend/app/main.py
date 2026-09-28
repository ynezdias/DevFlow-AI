from time import perf_counter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.metrics import router as metrics_router
from sqlalchemy import text

from app.api.reviews import router as reviews_router
from app.api.webhooks import router as webhooks_router
from app.db.session import engine


app = FastAPI(
    title="DevFlow AI",
    description="AI-powered pull request review platform",
    version="0.1.0",
)


app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
                   allow_methods=["GET"], allow_headers=["Content-Type"])
app.include_router(metrics_router)
app.include_router(reviews_router)
app.include_router(webhooks_router)


@app.middleware("http")
async def request_timing(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(perf_counter() - start)*1000:.3f}"
    return response


@app.get("/")
def root():
    return {
        "service": "DevFlow AI",
        "status": "running",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        database_status = "healthy"

    except Exception:
        database_status = "unhealthy"

    return {
        "service": "DevFlow AI",
        "status": "healthy"
        if database_status == "healthy"
        else "degraded",
        "database": database_status,
    }
