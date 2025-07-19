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
    'rest_framework_simplejwt.token_blacklist',
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

from fastapi import FastAPI, Depends, Cookie
from fastapi.security import OpenIdConnect
from fastapi.middleware.cors import CORSMiddleware
from api.routers import organizations, organization_types, effector_types, facilities, communes, departments, entries, effectors, auth
from django.conf import settings

oidc = OpenIdConnect(openIdConnectUrl=settings.OPEN_ID_CONNECT_URL)


app = FastAPI(
    swagger_ui_init_oauth = {
        "clientId": settings.OPENAPI_CLIENT_ID, 
        "appName": "Doc Tools", 
        "usePkceWithAuthorizationCodeGrant": True, 
        "scopes": "openid",
    }
)

origins = settings.CORS_ALLOWED_ORIGINS
logger.debug(f"{origins=}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/foo")
async def bar(token = Depends(oidc)):
    return token

@app.get("/get-cookie")
def get_cookie(mycookie: str = Cookie(None)):
    return {"mycookie": mycookie}