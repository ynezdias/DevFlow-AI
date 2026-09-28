from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import ReviewJob

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(ReviewJob.status, func.count()).group_by(ReviewJob.status)).all())
    return {"total_reviews": sum(counts.values()), **{key: counts.get(key, 0)
        for key in ("queued", "processing", "completed", "failed", "superseded")}}
