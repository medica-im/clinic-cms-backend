FROM python:3.14-slim-trixie AS prod

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

ARG DEBIAN_FRONTEND=noninteractive
# A new APT_REFRESH (build-push-prod.sh passes the date) reruns this layer, so
# Debian security updates land even when the base image has not changed.
ARG APT_REFRESH
RUN echo "apt refresh: $APT_REFRESH" \
 && apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
    locales \
    tzdata \
    procps \
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

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    gettext \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade -r /app/requirements/development.txt
RUN pip install --no-cache-dir -r /app/requirements/test.txt
