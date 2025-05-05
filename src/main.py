# Let Django knows where the project's settings is.
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from django.apps import apps
# Load the needed apps
apps.populate(installed_apps=[
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sites',
    'rest_framework_simplejwt.token_blacklist',
    'directory',
])
# Make sure the above apps were loaded
apps.check_apps_ready()
apps.check_models_ready()

from fastapi import FastAPI
from api.routers import organizations

app = FastAPI()

app.include_router(organizations.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}