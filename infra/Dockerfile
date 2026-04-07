FROM python:3.11-slim

EXPOSE 8000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

RUN python -m pip install --no-cache-dir uv

WORKDIR /app
COPY ai_module /app/ai_module

WORKDIR /app/ai_module
RUN uv sync --no-dev

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

CMD ["uv", "run", "uvicorn", "ai_module.main:app", "--host", "0.0.0.0", "--port", "8000"]
