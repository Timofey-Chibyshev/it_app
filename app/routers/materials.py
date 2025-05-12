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
        .options(selectinload(models.Subject.groups))
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()

    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Для преподавателя проверяем владение предметом
    if user.role == "teacher":
        teacher = await db.execute(select(models.Teacher).where(models.Teacher.user_id == user.id))
        teacher = teacher.scalar()
        if not teacher or subject.teacher_id != teacher.user_id:
            raise HTTPException(403, "Forbidden for teachers")

    # Для студента проверяем принадлежность к группе предмета
    if user.role == "student":
        student = await db.execute(
            select(models.Student)
            .options(selectinload(models.Student.group))
            .where(models.Student.user_id == user.id)
        )
        student = student.scalar()
        if not student or student.group_id not in [g.id for g in subject.groups]:
            raise HTTPException(403, "Forbidden for students")

    return subject



@router.get("/", response_class=HTMLResponse)
async def materials_page(
        subject_id: int,
        request: Request,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    try:
        subject = await get_subject_with_check(db, subject_id, current_user)
    except HTTPException as e:
        return RedirectResponse(f"/?error={e.detail}", status_code=303)

    # Остальной код получения материалов остается без изменений
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
            "current_user": current_user,
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

        # Определяем тип материала для пути
        folder = "lectures" if material_type == "lecture" else "practices"

        # Создаем путь для сохранения
        file_dir = Path(UPLOAD_DIR) / f"subject_{subject_id}" / folder
        file_dir.mkdir(parents=True, exist_ok=True)

        # Генерируем имя файла
        file_ext = Path(file.filename).suffix
        file_name = f"{uuid.uuid4()}{file_ext}"
        file_path = file_dir / file_name

        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Сохраняем относительный путь в БД
        relative_path = file_path.relative_to(UPLOAD_DIR)

        new_material = models.CourseMaterial(
            title=title,
            description=description,
            type=material_type,
            file_path=str(relative_path),  # Сохраняем относительный путь
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


from fastapi.responses import FileResponse  # Добавить импорт


@router.get("/download/{material_id}")
async def download_material(
        subject_id: int,
        material_id: int,
        db: AsyncSession = Depends(database.get_db),
        current_user: models.User = Depends(get_current_user)
):
    material = await db.execute(
        select(models.CourseMaterial)
        .options(selectinload(models.CourseMaterial.subject))
        .where(models.CourseMaterial.id == material_id)
    )
    material = material.scalar()

    if not material:
        raise HTTPException(404, "Material not found")

    # Полный путь к файлу
    full_path = Path(UPLOAD_DIR) / material.file_path

    if not full_path.exists():
        logger.error(f"File not found: {full_path}")
        raise HTTPException(404, "File not found")

    return FileResponse(
        full_path,
        filename=f"{material.title}{full_path.suffix}",
        media_type="application/octet-stream"
    )