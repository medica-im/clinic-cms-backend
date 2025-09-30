import logging, os
import logging.config
import colorlog
from datetime import timedelta
from django.utils.log import DEFAULT_LOGGING
from pathlib import Path
from decouple import Config, RepositoryEnv, AutoConfig, Csv
from django.utils.translation import gettext_lazy as _
from neomodel import config as neomodel_config

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(BASE_DIR)
config = AutoConfig(search_path = CONFIG_DIR)

# We do not set the SITE_ID so that the http request's host name is used to
# determine which organization's data to return
#SITE_ID =

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', cast=bool, default=False)

LOG_LEVEL = config('DJANGO_LOG_LEVEL', default='DEBUG')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {funcName} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {module} {funcName} {message}",
            "style": "{",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
}

ADMIN = config('ADMIN', cast=Csv(post_process=tuple))
ADMINS = [ADMIN]
MANAGERS = ADMINS

ALLOWED_HOSTS = ['*']
#ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# Application definition

INSTALLED_APPS = [
    # to use the admin integration, modeltranslation must be put before
    # django.contrib.admin
    'modeltranslation',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.postgres',
    'rest_framework',
    'rest_framework.authtoken',
    'easy_thumbnails',
    'addressbook',
    'taggit',
    'taggit_labels',
    'crispy_forms',
    'crispy_bootstrap5',
    'simple_history',
    # local apps
    'backend',
    'accounts',
    'facility',
    'mesh',
    'workforce',
    'staff',
    'directory',
    'access',
    'opengraph',
    'nlp',
    'heatwave',
]

if DEBUG:
    INSTALLED_APPS += [
        'django_extensions',
        'corsheaders',
    ]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.contrib.sites.middleware.CurrentSiteMiddleware',
]

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv())
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', cast=bool, default=False)

ROOT_URLCONF = config('ROOT_URLCONF')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': config('POSTGRES_HOST', default='database_development'),
        'NAME': config('POSTGRES_DB', default='postgres'),
        'USER': config('POSTGRES_USER', default='postgres'),
        'PASSWORD': config('POSTGRES_PASSWORD', default=''),
        #'PORT': config('DATABASE_PORT', cast=int, default=5432),
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'fr'

LANGUAGES = [
    ('fr', _('French')),
    ('en', _('English')),
]

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = config('STATIC_URL')
STATIC_ROOT = config('STATIC_ROOT')

MEDIA_ROOT = config('MEDIA_ROOT')

MEDIA_URL = '/media/'

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST FRAMEWORK
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'accounts.exceptions.core_exception_handler',
    'NON_FIELD_ERRORS_KEY': 'error',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
}

# DEFAULT USER MODEL
AUTH_USER_MODEL = 'accounts.User'

CRISPY_FAIL_SILENTLY = not DEBUG
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv())

THUMBNAIL_ALIASES = {
    'addressbook.Contact.profile_image': {
        'avatar_facebook': {'size': (170, 170), 'crop': False},
        'avatar_linkedin_twitter': {'size': (400, 400), 'crop': False},
    },
    'facility.Organization.logo': {
        'avatar_facebook': {'size': (170, 170), 'crop': False},
        'avatar_linkedin_twitter': {'size': (400, 400), 'crop': False},
    }
}

DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage'
AVATAR_FILE_STORAGE = config('AVATAR_FILE_STORAGE', default="")

# Redis
REDIS_HOST = config('REDIS_HOST', default='redis_development')
REDIS_PORT = config('REDIS_PORT', cast=str, default='6379')
REDIS_DATABASE_ID = config('REDIS_DATABASE_ID', default='0')
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://" + REDIS_HOST + ":" + REDIS_PORT + "/" + REDIS_DATABASE_ID,
    }
}

#Email
DEFAULT_FROM_EMAIL=config('DEFAULT_FROM_EMAIL', default="webmaster@localhost")
EMAIL_HOST=config('EMAIL_HOST')
EMAIL_PORT=config('EMAIL_PORT')
EMAIL_HOST_USER=config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD=config('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS=True
#EMAIL_USE_SSL
#EMAIL_TIMEOUT
#EMAIL_SSL_KEYFILE
#EMAIL_SSL_CERTFILE

# neo4j
NEO4J_URI = config('NEO4J_URI', default="neo4j://localhost:7687")
NEO4J_DATABASE = config('NEO4J_DATABASE')
NEO4J_USERNAME = config('NEO4J_USERNAME', default="neo4j")
NEO4J_PASSWORD = config('NEO4J_PASSWORD', default="neo4j")
NEO4J_AUTH = (NEO4J_USERNAME, NEO4J_PASSWORD)
NEO4J_7687_EXTERNAL_PORT= config('{NEO4J_7687_EXTERNAL_PORT}', default='7687')
neo4j_log = logging.getLogger("neo4j")
neo4j_log.setLevel(logging.ERROR)

#neomodel
TASTYPIE_FULL_DEBUG = True
neomodel_config.DATABASE_URL = f"bolt://{NEO4J_USERNAME}:{NEO4J_PASSWORD}@neo4j:{NEO4J_7687_EXTERNAL_PORT}"

#heatwave
PUBLIC_API_METEOFRANCE = config('PUBLIC_API_METEOFRANCE')
PUBLIC_API_METEOFRANCE_TTL = config('PUBLIC_API_METEOFRANCE_TTL', cast=int, default=600)

LOGIN_URL = '/admin/login/'

# FAST API JWT
JWT_SECRET_KEY=config('JWT_SECRET_KEY')
ACCESS_TOKEN_EXPIRE_MINUTES=config('ACCESS_TOKEN_EXPIRE_MINUTES', cast=int, default=30)
OIDC_GOOGLE_CLIENT_ID=config('OIDC_GOOGLE_CLIENT_ID')