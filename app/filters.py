from datetime import datetime, timedelta

from pathlib import Path
def time_left(delta: timedelta) -> str:
    if delta.total_seconds() < 0:
        return "Время истекло"

    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60

    parts = []
    if days > 0:
        parts.append(f"{days} д.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes} мин.")

    return " ".join(parts) or "Менее минуты"


def filename(path: str) -> str:
    return Path(path).name if path else ""