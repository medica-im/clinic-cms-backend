# Let Django knows where the project's settings is.
import os, sys
import logging
from logging.config import dictConfig
from fastapi_log_conf import log_config

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
#dictConfig(log_config)
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from django.apps import apps
# Load the needed apps
apps.populate(installed_apps=[
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sites',
    'accounts',
    'directory',
    'easy_thumbnails',
    'access',
    'addressbook',
    'workforce',
    'facility',
])
# Make sure the above apps were loaded
apps.check_apps_ready()
apps.check_models_ready()

from fastapi import FastAPI, Request, Cookie
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routers import organizations, organization_types, effector_types, facilities, communes, departments, entries, effectors, auth, phones, monkeys, emails, websites, payment_methods
from django.conf import settings
from fastapi_nextauth_jwt.exceptions import MissingTokenError

app = FastAPI()

origins = settings.CORS_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(organizations.router)
app.include_router(organization_types.router)
app.include_router(effector_types.router)
app.include_router(facilities.router)
app.include_router(communes.router)
app.include_router(departments.router)
app.include_router(entries.router)
app.include_router(effectors.router)
app.include_router(auth.router)
app.include_router(phones.router)
app.include_router(monkeys.router)
app.include_router(emails.router)
app.include_router(websites.router)
app.include_router(payment_methods.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.exception_handler(MissingTokenError)
async def unicorn_exception_handler(request: Request, exc: MissingTokenError):
    return JSONResponse(
        status_code=401,
        content={"message": "Oops! We couldn't find a cookie with a proper JWT token. Authenticate first."},
    )