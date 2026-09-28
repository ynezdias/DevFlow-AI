from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.review_job import ReviewJob
from app.models.finding import Finding
from app.schemas.finding import FindingResponse
from app.schemas.review_job import ReviewJobCreate, ReviewJobResponse


router = APIRouter(
    prefix="/api/reviews",
    tags=["reviews"],
)


@router.get("")
def list_reviews(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(ReviewJob))
    reviews = db.scalars(select(ReviewJob).order_by(ReviewJob.created_at.desc(), ReviewJob.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    fields = ("id", "repository_name", "pull_request_number", "head_sha", "status", "created_at",
              "started_at", "completed_at", "error_code", "publication_status", "github_check_run_id")
    items = []
    for review in reviews:
        report = (review.scope_summary or {}).get("report")
        items.append({**{field: getattr(review, field) for field in fields},
            "finding_count": report["summary"]["total_findings"] if report else None})
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post(
    "",
    response_model=ReviewJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    payload: ReviewJobCreate,
    db: Session = Depends(get_db),
):
    review = ReviewJob(
        repository_name=payload.repository_name,
        pull_request_number=payload.pull_request_number,
        head_sha=payload.head_sha,
    )

    db.add(review)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review already exists for this commit.",
        )

    db.refresh(review)

    return review


@router.get(
    "/{review_id}",
    response_model=ReviewJobResponse,
)
def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
):
    review = db.scalar(
        select(ReviewJob).where(ReviewJob.id == review_id)
    )

    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    return review

@router.get("/{review_id}/findings", response_model=list[FindingResponse])
def get_review_findings(review_id: UUID, db: Session = Depends(get_db)):
    if db.get(ReviewJob, review_id) is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return db.scalars(select(Finding).where(Finding.review_job_id == review_id).order_by(
        Finding.file_path, Finding.line_number, Finding.source, Finding.category
    )).all()


@router.get("/{review_id}/report")
def get_review_report(review_id: UUID, db: Session = Depends(get_db)):
    review = db.get(ReviewJob, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    report = (review.scope_summary or {}).get("report")
    if not report or review.status not in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail="Validated report is not available for this review.")
    return report
