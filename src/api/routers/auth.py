import logging
import os
from typing import Annotated
from datetime import timedelta
from django.contrib.auth import get_user_model
from fastapi import APIRouter, Security, HTTPException, status, Request, Response, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi_jwt import (
    JwtAccessBearer,
    JwtAuthorizationCredentials,
    JwtRefreshBearer,
)
from django.conf import settings
from api.utils import get_site_from_request
from api.auth import get_user, get_role
from fastapi_nextauth_jwt import NextAuthJWT
from accounts.models import User

logger = logging.getLogger(__name__)


router = APIRouter()
auth_secret=os.getenv("AUTH_SECRET")
if auth_secret:
    JWT = NextAuthJWT(
        secret=auth_secret,
        csrf_prevention_enabled=False
    )

# Read access token from bearer header and cookie (bearer priority)
access_security = JwtAccessBearer(
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

@router.get("/jwt")
async def return_jwt(jwt: Annotated[dict, Depends(JWT)], request: Request):
    logger.info(request.client)
    logger.info(request.headers)
    logger.info(request.cookies)
    logger.debug(request.cookies.get('__Secure-authjs.session-token'))
    try:
        return {"message": f"Hi {jwt['name']}. Greetings from fastapi!"}
    except Exception as e:
        logger.debug(e)

@router.delete("/delete")
async def return_jwt_delete(jwt: Annotated[dict, Depends(JWT)], request: Request):
    try:
        return {"message": f"Hi {jwt['name']}. Greetings from fastapi!"}
    except Exception as e:
        logger.debug(e)

@router.post("/post")
async def test_jwt_post(jwt: Annotated[dict, Depends(JWT)], request: Request):
    try:
        return {"message": f"Hi {jwt['name']}. Greetings from fastapi!"}
    except Exception as e:
        logger.debug(e)

@router.get("/auth")
async def auth_google(jwt: Annotated[dict, Depends(JWT)], request: Request, redirect: str|None, response_class=RedirectResponse):
    user_infos = jwt
    logger.debug(user_infos)
    # Here you would typically:
    # 1. Check if the user exists in your database
    try:
        site = await get_site_from_request(request)
        logger.debug(site)
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
    logger.debug(f"{access_token=}")
    refresh_token = refresh_security.create_refresh_token(subject=subject)
    logger.debug(f"{refresh_token=}")
    if redirect:
        response = RedirectResponse(url=f"/{redirect}")
    else:
        response = JSONResponse({"success" : "true"}, status_code=200)
    access_security.set_access_cookie(response, access_token)
    access_security.set_refresh_cookie(response, refresh_token)
    """
    response.set_cookie(
        key="refresh-token",
        value=refresh_token,
        path="/",
        httponly=True,
        secure=True,
        samesite='strict'
    )
    response.set_cookie(
        key="access-token",
        value=access_token,
        path="/",
        httponly=True,
        secure=True,
        samesite='strict'
    )
    """
    return response

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
async def read_current_user(
        jwt: Annotated[dict, Depends(JWT)], request: Request
):  
    site = await get_site_from_request(request)
    try:
        django_user = await User.objects.select_related('grammatical_gender', 'role', 'site').aget(email=jwt["email"])
    except User.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Insufficient permissions"
        )
    role = await get_role(django_user, site)
    gg = getattr(
        getattr(django_user, "grammatical_gender", None),
        "code",
        None
    )
    effector = getattr(
        getattr(django_user, "effector", None),
        "hex",
        None
    )
    full_name = getattr(django_user, "full_name", None)
    return {
        "name": jwt["name"],
        "email": jwt["email"],
        "picture": jwt["picture"],
        "role": role.name,
        "gender": gg,
        "effector": effector,
        "full_name": full_name
    }

