FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ ./agent/
ENV PORT=8001
EXPOSE $PORT
CMD ["sh", "-c", "uvicorn agent.main:app --host 0.0.0.0 --port $PORT"]