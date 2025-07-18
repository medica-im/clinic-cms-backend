import logging
from datetime import timedelta
from django.contrib.auth import get_user_model
from fastapi import APIRouter, Security, HTTPException, status, Request
from fastapi_jwt import (
    JwtAccessBearerCookie,
    JwtAuthorizationCredentials,
    JwtRefreshBearer,
)
from django.conf import settings
from directory.utils import get_site_from_hostname

logger = logging.getLogger(__name__)

User=get_user_model()

router = APIRouter()

# Read access token from bearer header and cookie (bearer priority)
access_security = JwtAccessBearerCookie(
    secret_key=settings.JWT_SECRET_KEY,
    auto_error=False,
    access_expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)  # change access token validation timedelta
)
# Read refresh token from bearer header only
refresh_security = JwtRefreshBearer(
    secret_key=settings.JWT_SECRET_KEY, 
    auto_error=True  # automatically raise HTTPException: HTTP_401_UNAUTHORIZED 
)

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

def get_user_infos_from_google_token(id_token_str):
    # Verify the token and get user info
    id_info = id_token.verify_oauth2_token(
        id_token_str, 
        google_requests.Request(), 
        settings.OIDC_GOOGLE_CLIENT_ID
    )
    user_infos = {
        'id': id_info['sub'],  # Google's unique identifier for the user
        'email': id_info.get('email'),
    }
    if not user_infos:
        return {
            "status": False,
            "user_infos": user_infos
        }
    return {
        "status": True,
        "user_infos": user_infos
    }

@router.get("/google")
async def auth_google(request: Request, credential: str|None = None):
    logger.debug(f"{credential=}")
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No credential provided."
        )

    # Verify the Google token
    check = get_user_infos_from_google_token(credential)
    if check['status'] is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid credential"
        )

    user_infos = check['user_infos']

    # Here you would typically:
    # 1. Check if the user exists in your database
    try:
        site = await get_site_from_hostname(request.url.hostname)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Unauthorized client"
        )
    try:
        user = await User.objects.aget(email=user_infos['email'], site=site)
        logger.debug(user)
    except User.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Unknown user"
        )
    # 2. Create a new user if they don't exist
    # 3. Generate your application's JWT token
    subject={"sub": user_infos['email']}
    access_token = access_security.create_access_token(subject=subject)
    refresh_token = refresh_security.create_refresh_token(subject=subject)
    return {"access_token": access_token, "refresh_token": refresh_token}

@router.post("/auth")
def auth():
    # subject (actual payload) is any json-able python dict
    subject = {"username": "username", "role": "user"}

    # Create new access/refresh tokens pair
    access_token = access_security.create_access_token(subject=subject)
    refresh_token = refresh_security.create_refresh_token(subject=subject)
    return {"access_token": access_token, "refresh_token": refresh_token}

@router.post("/refresh")
def refresh(
        credentials: JwtAuthorizationCredentials = Security(refresh_security)
):
    # Update access/refresh tokens pair
    # We can customize expires_delta when creating
    access_token = access_security.create_access_token(subject=credentials.subject)
    refresh_token = refresh_security.create_refresh_token(subject=credentials.subject, expires_delta=timedelta(days=2))

    return {"access_token": access_token, "refresh_token": refresh_token}

@router.get("/users/me")
def read_current_user(
        credentials: JwtAuthorizationCredentials = Security(access_security)
):  
    # auto_error=False, so we should check manually
    if not credentials:
        raise HTTPException(status_code=401, detail='my-custom-details')

    # now we can access Credentials object
    return {"username": credentials["username"], "role": credentials["role"]}