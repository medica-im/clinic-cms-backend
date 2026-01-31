from pydantic import ValidationError


def log_oidc(jwt, site):
    from .models import OIDC
    oidc_entry = OIDC(
        iss=jwt.get('iss', ''),
        aud=jwt.get('aud', ''),
        sub=jwt.get('sub', ''),
        iat=jwt.get('iat', 0),
        email=jwt.get('email', ''),
        email_verified=jwt.get('email_verified')=="",
        name=jwt.get('name', ''),
        picture=jwt.get('picture', ''),
        given_name=jwt.get('given_name', ''),
        family_name=jwt.get('family_name', ''),
        locale=jwt.get('locale', ''),
        jti=jwt.get('jti')
        site=site
    )
    try:
        oidc_entry.save()
    except ValidationError as e:
        pass