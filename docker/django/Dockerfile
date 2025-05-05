FROM python:3.12-bullseye AS prod

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

#ENV DOCKER_CONTAINER=1

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get clean && apt-get update && apt-get install --no-install-recommends -y \
    locales \
    build-essential \
    python3-yaml \
    binutils
 
RUN echo "Europe/Paris" > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata && \
#    sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i -e 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen && \
    echo 'LANG="fr_FR.UTF-8"'>/etc/default/locale && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=fr_FR.UTF-8

RUN locale -a
ENV LANG=fr_FR.UTF-8
ENV LANGUAGE=fr_FR
ENV LC_ALL=fr_FR.UTF-8

ADD ./requirements /app/requirements
RUN pip install pip --upgrade
RUN pip install -r /app/requirements/common.txt

RUN mkdir /var/log/celery && touch /var/log/celery/celery.log
RUN mkdir /var/log/gunicorn && touch /var/log/gunicorn/gunicorn.log

ENV DJANGO_SETTINGS_MODULE=app.settings

FROM prod AS dev

RUN apt-get clean && apt-get update && apt-get install -y \
    postgresql-client \
    gettext \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade -r /app/requirements/development.txt
