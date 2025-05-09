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

router = APIRouter(prefix="/subjects/{subject_id}/materials", tags=["materials"])

UPLOAD_DIR = "uploads"
Path(UPLOAD_DIR).mkdir(exist_ok=True)

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



@router.get("/", response_class=HTMLResponse)
async def materials_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    subject = await get_subject_with_check(db, subject_id, current_user)

    materials = (await db.execute(
        select(models.CourseMaterial)
        .options(
            selectinload(models.CourseMaterial.group),
            selectinload(models.CourseMaterial.submissions))
        .where(models.CourseMaterial.subject_id == subject_id)
    )).scalars().all()

    return templates.TemplateResponse(
        "subjects/materials.html",
        {
            "request": request,
            "subject": subject,
            "materials": materials,
            "groups": subject.groups,
            "current_time": datetime.now(),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success")
        }
    )


@router.post("/")
async def create_material(
        subject_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(None),
        material_type: str = Form(...),
        group_id: int = Form(...),
        deadline: datetime = Form(None),
        file: UploadFile = File(...),
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        subject = await get_subject_with_check(db, subject_id, current_user)

        if material_type == "assignment" and not deadline:
            raise HTTPException(400, "Deadline required for assignments")

        # Сохранение файла
        file_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}" / f"group_{group_id}"
        file_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"{uuid.uuid4()}{Path(file.filename).suffix}"
        file_path = file_dir / file_name

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Создание записи
        new_material = models.CourseMaterial(
            title=title,
            description=description,
            type=material_type,
            file_path=str(file_path),
            subject_id=subject_id,
            group_id=group_id,
            deadline=deadline
        )

        db.add(new_material)
        await db.commit()

        return RedirectResponse(
            f"/subjects/{subject_id}/materials?success={file.filename}",
            status_code=303
        )

    except Exception as e:
        return RedirectResponse(
            f"/subjects/{subject_id}/materials?error={str(e)}",
            status_code=303
        )
