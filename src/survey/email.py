from django.core.mail import send_mail
from django.conf import settings

def send_email_alert(survey, response):
    url=(
        f'https://{survey.site.domain}/accounts/login'
        f'?redirect=/enquete/{survey.name}/{response.id}'
    )
    subject=f'Nouvelle contribution nº {response.id} pour "{survey.label}".'
    message=(
        f'Merci de modérer la contribution nº{response.id} pour' 
        f'l\'enquête "{survey.label}":\n'
        f'{url}'
    )
    from_email=settings.DEFAULT_FROM_EMAIL
    to_email = [moderator.email for moderator in survey.moderators.all()]
    send_mail(
        subject,
        message,
        from_email,
        to_email,
        fail_silently=False,
    )