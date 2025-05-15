FROM python:3.10

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем ВСЕ содержимое, включая app/
COPY . .

RUN mkdir -p /uploads/assignments && \
    chmod -R 755 /uploads

# Точка входа теперь в docker-compose