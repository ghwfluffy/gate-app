FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace/api

COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY api/ /workspace/api/
COPY www/ /workspace/www/
COPY vendor/federated-banner/ /workspace/vendor/federated-banner/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
