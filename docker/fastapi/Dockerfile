FROM python:3.13-slim
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
WORKDIR /app
ADD ./requirements /app/requirements

RUN pip install --no-cache-dir -r /app/requirements/common.txt
RUN pip install --no-cache-dir -r /app/requirements/fastapi.txt
