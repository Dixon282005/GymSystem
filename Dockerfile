FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GYMSIS_RUN_MODE=web \
    GYMSIS_HOST=0.0.0.0 \
    GYMSIS_PORT=8550 \
    GYMSIS_WEB_RENDERER=canvaskit

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8550

CMD ["python", "main.py"]
