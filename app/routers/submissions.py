from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Form,
    status,
    UploadFile,
    File
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pathlib import Path
import sys
import shutil
import uuid
# Добавляем путь к корневой директории проекта
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))
from datetime import datetime

from app.models import models
from app.schemas import schemas
from app import database
from app.auth import get_current_user
from app.dependencies import templates
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects/{subject_id}/submissions", tags=["submissions"])

async def get_subject_with_check(db: AsyncSession, subject_id: int, user: models.User):
    subject = await db.execute(
        select(models.Subject)
        .options(selectinload(models.Subject.teacher))
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    if user.role != "teacher" or subject.teacher.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return subject

@router.get("/{subject_id}/submissions", response_class=HTMLResponse)
async def view_submissions(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_check(db, subject_id, current_user)

    submissions = (await db.execute(
        select(models.AssignmentSubmission)
        .options(
            selectinload(models.AssignmentSubmission.material),
            selectinload(models.AssignmentSubmission.student))
        .join(models.CourseMaterial)
        .where(models.CourseMaterial.subject_id == subject_id)
    )).scalars().all()

    return templates.TemplateResponse(
        "subjects/submissions.html",
        {"request": request, "subject": subject, "submissions": submissions}
    )