from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.review_job import ReviewJob
from app.schemas.review_job import ReviewJobCreate, ReviewJobResponse


router = APIRouter(
    prefix="/api/reviews",
    tags=["reviews"],
)


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