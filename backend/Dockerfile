FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # `migrations/env.py` importa `backend.src...`: el padre de backend/ tiene
    # que estar en el path para que alembic encuentre el paquete.
    PYTHONPATH=/app

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Migraciones y luego la API. En Linux no aplica la trampa del
# ProactorEventLoop de Windows, así que no hace falta --reload.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
