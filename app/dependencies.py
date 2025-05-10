from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Инициализируем шаблоны ДО создания фильтров
templates = Jinja2Templates(directory="app/templates")

def configure_jinja_filters():
    logger.info("Configuring Jinja2 filters")
    
    def datetime_filter(value, fmt="%d.%m.%Y %H:%M"):
        if isinstance(value, datetime):
            return value.strftime(fmt)
        return value

    def duration_filter(delta):
        if isinstance(delta, timedelta):
            total_seconds = delta.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours} ч {minutes} мин" if hours > 0 else f"{minutes} мин"
        return delta

    def auditory_filter(group_number):
        try:
            return f"Ауд. {group_number[:2]}{ord(group_number[-1]) % 10}"
        except Exception as e:
            logger.error(f"Error in auditory filter: {str(e)}")
            return "Ауд. 000"

    # Явная регистрация фильтров
    templates.env.filters["datetime_format"] = datetime_filter
    templates.env.filters["duration_format"] = duration_filter
    templates.env.filters["auditory_from_group"] = auditory_filter
    templates.env.filters["filename"] = lambda path: Path(path).name
    templates.env.filters["ru_type"] = lambda t: {"lecture": "Лекция", "practice": "Практика"}.get(t, t)

    logger.info("Jinja2 filters configured successfully")

# Вызываем сразу при импорте
configure_jinja_filters()


from .filters import time_left, filename

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["time_left"] = time_left
templates.env.filters["filename"] = filename

templates.env.filters['ru_status'] = lambda s: {
    'submitted': 'Отправлено',
    'graded': 'Оценено',
    'rejected': 'Отклонено'
}.get(s, s)
