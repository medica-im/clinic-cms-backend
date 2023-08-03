import logging, os
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

LOG_LEVEL = config('LOG_LEVEL', default='DEBUG')

DICT_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    "formatters": {
        "default": {
            "format": "%(asctime)s %(name)s %(pathname)s:%(lineno)s:%(funcName)s %(levelname)s %(message)s",
        },
        "django.server": DEFAULT_LOGGING['formatters']['django.server'],
    },

    "handlers": {
        'console': {
            'level': LOG_LEVEL,
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'filters': ['require_debug_true'],
    },
        "console_debug_false": {
            "level": LOG_LEVEL,
            "filters": ["require_debug_false"],
            "class": "logging.StreamHandler",
        },

        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler"
        },
        #"applogfile": {
        #    "level": "DEBUG",
        #    "class": "logging.FileHandler",
        #    "filename": LOG_FILE,
        #},
        "django.server": DEFAULT_LOGGING["handlers"]["django.server"],
    },

    "loggers": {
        '': {
            'level': LOG_LEVEL,
            'handlers': ['console', 'console_debug_false',],
            'propagate': True,
        },
        "django": {
            "handlers": [
                "console",
                "console_debug_false",
                "mail_admins",
            ],
            "level": LOG_LEVEL,
        },
        "bot.stream": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "bot.tasks": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "bot.doctoctocbot": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "messenger.tasks": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "tagging.tasks": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "timeline": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "django-invitations": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "bot.bin.thread": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "moderation.tasks": {
            "handlers": ["console", "console_debug_false", "mail_admins"],
            "level": LOG_LEVEL,
        },
        "django.server": DEFAULT_LOGGING["loggers"]["django.server"],
    },
}
logging.config.dictConfig(DICT_CONFIG)

ADMIN = config('ADMIN', cast=Csv(post_process=tuple))
ADMINS = [ADMIN]
MANAGERS = ADMINS

ALLOWED_HOSTS = ['*']

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
    'rest_framework_simplejwt',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'easy_thumbnails',
    'constance.backends.database',
    'constance',
    'addressbook',
    'taggit',
    'taggit_labels',
    'crispy_forms',
    'crispy_bootstrap5',
    'simple_history',
    #wagtail
    'wagtail.contrib.forms',
    'wagtail.contrib.redirects',
    'wagtail.embeds',
    'wagtail.sites',
    'wagtail.users',
    'wagtail.snippets',
    'wagtail.documents',
    'wagtail.images',
    'wagtail.search',
    'wagtail.admin',
    'wagtail',
    'wagtail.api.v2',
    'modelcluster',
    # local apps
    'backend',
    'accounts',
    'facility',
    'mesh',
    'workforce',
    'staff',
    'directory',
    'access',
    'contact',
    'opengraph',
    'cms',
    'nlp',
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
    'wagtail.contrib.redirects.middleware.RedirectMiddleware',
    'django.contrib.sites.middleware.CurrentSiteMiddleware',
]

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv())

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
        'rest_framework_simplejwt.authentication.JWTAuthentication',
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

SHELL_PLUS = "ipython"

SHELL_PLUS_PRINT_SQL = True

NOTEBOOK_ARGUMENTS = [
    "--ip",
    "0.0.0.0",
    "--port",
    "8888",
    "--allow-root",
    "--no-browser",
]

IPYTHON_ARGUMENTS = [
    "--ext",
    "django_extensions.management.notebook_extension",
    "--debug",
]

IPYTHON_KERNEL_DISPLAY_NAME = "Django Shell-Plus"

#SHELL_PLUS_POST_IMPORTS = [ # extra things to import in notebook
#    ("module1.submodule", ("func1", "func2", "class1", "etc")),
#    ("module2.submodule", ("func1", "func2", "class1", "etc"))
#]

THUMBNAIL_ALIASES = {
    'addressbook.Contact.profile_image': {
        'avatar_facebook': {'size': (170, 170), 'crop': False},
        'avatar_linkedin_twitter': {'size': (400, 400), 'crop': False},
    },
}

DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage'
AVATAR_FILE_STORAGE = config('AVATAR_FILE_STORAGE', default="")

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    #'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}


# Redis
REDIS_HOST = config('REDIS_HOST', default='redis_development')
REDIS_PORT = config('REDIS_PORT', cast=str, default='6379')
REDIS_DATABASE_ID = config('REDIS_DATABASE_ID', default='0')
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://" + REDIS_HOST + ":" + REDIS_PORT + "/" + REDIS_DATABASE_ID,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

#Constance
CONSTANCE_BACKEND = 'constance.backends.database.DatabaseBackend'
CONSTANCE_DATABASE_CACHE_BACKEND = 'default'
CONSTANCE_IGNORE_ADMIN_VERSION_CHECK = True

CONSTANCE_CONFIG = {
    'ADMIN_SEARCH_CONFIG': (
        'french',
        'You can specify the config attribute to a SearchVector and '
        'SearchQuery to use a different search configuration. This allows '
        'using different language parsers and dictionaries as defined by the '
        'database'
    ),
    'CONTACT_NOSMOKING_RECIPIENT_LIST': (
        '',
        'List of email addresses separated by a comma.',
        str
    ),
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

#Wagtail
WAGTAIL_SITE_NAME = 'Healthcenter'

# neo4j
NEO4J_URI = config('NEO4J_URI', default="neo4j://localhost:7687")
NEO4J_DATABASE = config('NEO4J_DATABASE')
NEO4J_USERNAME = config('NEO4J_USERNAME', default="neo4j")
NEO4J_PASSWORD = config('NEO4J_PASSWORD', default="neo4j")
NEO4J_AUTH = (NEO4J_USERNAME, NEO4J_PASSWORD)
NEO4J_7687_EXTERNAL_PORT= config('{NEO4J_7687_EXTERNAL_PORT}', default='7687')

#neomodel
neomodel_config.DATABASE_URL = f"bolt://{NEO4J_USERNAME}:{NEO4J_PASSWORD}@neo4j:{NEO4J_7687_EXTERNAL_PORT}"