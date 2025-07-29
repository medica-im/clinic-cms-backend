# Let Django knows where the project's settings is.
import os
import logging

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
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
from api.routers import organizations, organization_types, effector_types, facilities, communes, departments, entries, effectors, auth, phones
from django.conf import settings
from fastapi_nextauth_jwt.exceptions import MissingTokenError

app = FastAPI()

origins = settings.CORS_ALLOWED_ORIGINS

"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

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

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get('/cookie')
async def get_cookie(request: Request):
    logger.debug(request.cookies.get('__Secure-authjs.session-token'))
    return request.cookies.get('__Secure-authjs.session-token')

@app.post('/cookie')
async def post_cookie(request: Request):
    logger.debug(request.cookies.get('__Secure-authjs.session-token'))
    return request.cookies.get('__Secure-authjs.session-token')

@app.exception_handler(MissingTokenError)
async def unicorn_exception_handler(request: Request, exc: MissingTokenError):
    return JSONResponse(
        status_code=401,
        content={"message": "Oops! We couldn't find a cookie with a proper JWT token. Authenticate first."},
    )