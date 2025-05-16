from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, or_, select, union_all
from sqlalchemy.orm import selectinload, aliased

from app.models import models
from app.dependencies import templates
from app.auth import get_current_user
from app import database

router = APIRouter(
    prefix="/search",
    tags=["search"]
)

@router.get("", response_class=HTMLResponse)
async def search_page(
    request: Request,
    current_user: models.User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "current_user": current_user}
    )

@router.get("/results")
async def search_results(
    query: str,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if len(query) < 3:
        return JSONResponse(content={"results": []})

    # Создаем базовые запросы с явной загрузкой связей
    stmt1 = (
        select(models.Subject)
        .options(selectinload(models.Subject.teacher))
        .where(models.Subject.name.ilike(f"%{query}%")))
    
    stmt2 = (
        select(models.Subject)
        .join(models.Teacher, models.Subject.teacher_id == models.Teacher.user_id)
        .join(models.User, models.Teacher.user_id == models.User.id)
        .options(selectinload(models.Subject.teacher))
        .where(
            or_(
                models.User.first_name.ilike(f"%{query}%"),
                models.User.last_name.ilike(f"%{query}%"),
                models.User.patronymic.ilike(f"%{query}%")
            )
        )
    )

    # Объединяем через UNION
    combined = union_all(stmt1, stmt2)
    
    # Создаем CTE и алиас для корректного маппинга
    cte = combined.cte("combined_subjects")
    subject_alias = aliased(models.Subject, cte)

    # Финальный запрос с загрузкой всех связей
    final_query = (
        select(subject_alias)
        .options(
            selectinload(subject_alias.teacher)
            .selectinload(models.Teacher.user)
        )
        .limit(20)
    )

    # Выполняем запрос
    result = await db.execute(final_query)
    subjects = result.unique().scalars().all()

    # Формируем результаты
    results = [
        {
            "id": subj.id,
            "name": subj.name,
            "type": subj.type,
            "teacher": (
                f"{subj.teacher.user.last_name} "
                f"{subj.teacher.user.first_name} "
                f"{subj.teacher.user.patronymic or ''}"
            ).strip(),
            "url": f"/subjects/{subj.id}/materials/"
        } for subj in subjects
    ]

    return JSONResponse(content={"results": results})
