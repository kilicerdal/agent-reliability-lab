FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ backend/
ENV PYTHONPATH=/app/backend PYTHONDONTWRITEBYTECODE=1
CMD ["python","-m","uvicorn","lab.api:app","--host","0.0.0.0","--port","8810"]
