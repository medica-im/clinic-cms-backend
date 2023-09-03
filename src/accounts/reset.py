from django.shortcuts import get_object_or_404
from django.views.generic.base import RedirectView


class PasswordResetConfirmRedirectView(RedirectView):

    permanent = False
    query_string = False
    pattern_name = 'password_reset_confirm'

    def get_redirect_url(self, *args, **kwargs):
        uidb64=kwargs['uidb64']
        token=kwargs['token']
        url = f"/accounts/reset/confirm/{uidb64}/{token}"
        return url