from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas.schemas import Submission, SubmissionCreate
from app.models.models import Submission as DBSubmission, Assignment, User
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/submissions", tags=["submissions"])

@router.post("/", response_model=Submission)
async def create_submission(
    submission: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка что студент имеет доступ к заданию
    assignment = await db.get(Assignment, submission.assignment_id)
    if not assignment or current_user not in assignment.subject.students:
        raise HTTPException(403, "Нет доступа к этому заданию")
    
    db_submission = DBSubmission(
        **submission.dict(),
        student_id=current_user.id,
        submitted_at=datetime.utcnow()
    )
    db.add(db_submission)
    await db.commit()
    return db_submission

@router.get("/assignment/{assignment_id}", response_model=list[Submission])
async def get_submissions(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка что преподаватель имеет доступ
    assignment = await db.get(Assignment, assignment_id)
    if not assignment or assignment.subject.teacher_id != current_user.id:
        raise HTTPException(403, "Доступ запрещен")
    
    result = await db.execute(select(DBSubmission).where(DBSubmission.assignment_id == assignment_id))
    return result.scalars().all()