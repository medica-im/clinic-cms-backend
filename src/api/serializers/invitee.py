import logging
from api.types.invitee import Invitee
from facility.models import Organization
from mailer.tasks import send_single_email_task
from django.contrib.sites.models import Site
from fastapi import status, HTTPException

logger = logging.getLogger(__name__)

async def notification_email(invitee: Invitee, site: Site):
    if not invitee.email:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No email"
        )
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site"
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid"
        )
    domain = site.domain
    subject = f"{organization.formatted_name} vous invite à utiliser le service {domain}"
    message = (
        f"Bonjour {invitee.name if invitee.name else ''}!\n\n"
        f"{organization.formatted_name} vous invite à créer un compte sur le "
        f"service en ligne {domain}. Vous pouvez vous rendre à l'adresse suivante:\n\n"
        f"https://{domain}/signin\n\n"
        f"et cliquer sur \"Se connecter avec Google\". Vous devez utiliser l'adresse "
        f"mail suivante: {invitee.email} Si vous n'avez pas de compte Google lié à "
        f"cette adresse, vous pourrez en créer un gratuitement en moins d'une minute. "
        f"Il n'est pas nécessaire de créer une adresse Gmail! Votre mail habituel {invitee.email} est suffisant.\n\n"
        f"""Si vous devez créer un compte Google, lors de l'étape "Méthode de connexion au compte", ne remplissez pas le champ "Nom d'utilisateur  ...@gmail.com". Cliquez sur "Utiliser l'adresse email existante".\n\n"""
        f"Après authentification par le service \"Se connecter avec Google\", votre "
        f"compte sur {domain} sera créé automatiquement. Vous pourrez utiliser nos "
        f"services et créer votre entrée dans l'annuaire de l'organisation.\n\n"
        f"En cas de problème, merci de nous contacter via https://{domain}/contact\n\n"
        "Si vous souhaitez utiliser une autre adresse électronique pour vous connecter à notre service, contactez-nous et nous vous enverrons une nouvelle invitation."
    )
    logger.debug(f"{invitee.email=} {subject=} {message=}")
    send_single_email_task.delay(invitee.email, subject, message)
