from fastapi import FastAPI
from sqlalchemy import text

from app.api.reviews import router as reviews_router
from app.db.session import engine


app = FastAPI(
    title="DevFlow AI",
    description="AI-powered pull request review platform",
    version="0.1.0",
)


app.include_router(reviews_router)


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