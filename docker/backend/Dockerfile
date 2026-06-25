FROM python:3.14-trixie AS prod

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get clean && apt-get update && apt-get install -y \
    locales \
    build-essential \
    python3-yaml \
    binutils \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    python3-pip \
    gcc \
    libglib2.0-dev \
    libgirepository1.0-dev \
    python3-cairo \
 && rm -rf /var/lib/apt/lists/*

RUN echo "Europe/Paris" > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata && \
    sed -i -e 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen && \
    echo 'LANG="fr_FR.UTF-8"'>/etc/default/locale && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=fr_FR.UTF-8

ENV LANG=fr_FR.UTF-8
ENV LANGUAGE=fr_FR
ENV LC_ALL=fr_FR.UTF-8

ADD ./requirements /app/requirements
RUN pip install pip --upgrade && pip --version
RUN pip install --no-cache-dir -r /app/requirements/common.txt
RUN pip install --no-cache-dir -r /app/requirements/fastapi.txt

RUN mkdir -p /var/log/celery && touch /var/log/celery/celery.log
RUN mkdir -p /var/log/gunicorn && touch /var/log/gunicorn/gunicorn.log

COPY ./src /app

FROM prod AS dev

RUN apt-get clean && apt-get update && apt-get install -y \
    postgresql-client \
    gettext \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade -r /app/requirements/development.txt
RUN pip install --no-cache-dir -r /app/requirements/test.txt
