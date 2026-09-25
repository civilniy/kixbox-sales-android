FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 TZ=Europe/Moscow
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY sections ./sections

EXPOSE 8095
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8095", "--proxy-headers"]
