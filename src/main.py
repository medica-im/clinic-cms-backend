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
    'accounts',
    'directory',
    'easy_thumbnails',
    'access',
    'addressbook',
    'workforce',
])
# Make sure the above apps were loaded
apps.check_apps_ready()
apps.check_models_ready()

from fastapi import FastAPI
from api.routers import organizations, organization_types, effector_types, facilities, communes, departments, entries, effectors

app = FastAPI()

app.include_router(organizations.router)
app.include_router(organization_types.router)
app.include_router(effector_types.router)
app.include_router(facilities.router)
app.include_router(communes.router)
app.include_router(departments.router)
app.include_router(entries.router)
app.include_router(effectors.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}