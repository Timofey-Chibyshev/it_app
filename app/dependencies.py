from fastapi.templating import Jinja2Templates
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Инициализируем шаблоны
templates = Jinja2Templates(directory="app/templates")

# Добавляем пользовательские фильтры
templates.env.filters['filename'] = lambda path: Path(path).name
templates.env.filters['ru_type'] = lambda t: {
    'lecture': 'Лекция',
    'practice': 'Практика'
}.get(t, t)