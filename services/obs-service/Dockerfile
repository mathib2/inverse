FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn numpy
WORKDIR /app
COPY core/inverse_core /app/inverse_core
COPY services/obs-service/app.py /app/app.py
ENV PYTHONPATH=/app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
