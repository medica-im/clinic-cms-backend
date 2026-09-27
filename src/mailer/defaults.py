"""Built-in email texts: the last resort when no EmailTemplate row is usable.

The default EmailTemplate row is seeded from these by a data migration, and
administrators edit that row, not this file. This copy only exists so that an
invitation still goes out when the row is deleted, deactivated or emptied.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateText:
    """The fields of an EmailTemplate that rendering needs, without a row."""

    subject: str
    body: str
    content_type: str = "text"
    body_text: str = ""


INVITATION_FALLBACK = TemplateText(
    subject="{{ organization_name }} vous invite à utiliser le service {{ site_name }}",
    body=(
        "Bonjour {{ invitee_name }}!\n\n"
        "{{ organization_name }} vous invite à créer un compte sur le service en "
        "ligne {{ site_name }}. Vous pouvez vous rendre à l'adresse suivante:\n\n"
        "{{ signin_url }}\n\n"
        "et cliquer sur \"Se connecter avec Google\". Vous devez utiliser l'adresse "
        "mail suivante: {{ invitee_email }} Si vous n'avez pas de compte Google lié "
        "à cette adresse, vous pourrez en créer un gratuitement en moins d'une "
        "minute. Il n'est pas nécessaire de créer une adresse Gmail! Votre mail "
        "habituel {{ invitee_email }} est suffisant.\n\n"
        "Si vous devez créer un compte Google, lors de l'étape \"Méthode de "
        "connexion au compte\", ne remplissez pas le champ \"Nom d'utilisateur  "
        "...@gmail.com\". Cliquez sur \"Utiliser l'adresse email existante\".\n\n"
        "Après authentification par le service \"Se connecter avec Google\", votre "
        "compte sur {{ site_name }} sera créé automatiquement. Vous pourrez "
        "utiliser nos services et créer votre entrée dans l'annuaire de "
        "l'organisation.\n\n"
        "En cas de problème, merci de nous contacter via {{ contact_url }}\n\n"
        "Si vous souhaitez utiliser une autre adresse électronique pour vous "
        "connecter à notre service, contactez-nous et nous vous enverrons une "
        "nouvelle invitation."
    ),
)


# The same invitation as email HTML. Tables and inline styles only: Gmail and
# Outlook drop or rewrite <style> blocks, and no remote resource is loaded,
# since mail clients block them by default. Not the seeded default yet -- an
# html part is only sent from step 2 on.
INVITATION_HTML = TemplateText(
    subject=INVITATION_FALLBACK.subject,
    content_type="html",
    body="""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Invitation — {{ organization_name }}</title>
</head>
<body style="margin:0; padding:0; background-color:#f3f4f6;">
<div style="display:none; max-height:0; overflow:hidden; opacity:0;">{{ organization_name }} vous invite à créer votre compte sur {{ site_name }}.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f3f4f6;">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; background-color:#ffffff; border:1px solid #e5e7eb; border-radius:8px;">
        <tr>
          <td style="padding:24px 32px; border-bottom:1px solid #e5e7eb; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#6b7280;">
            {{ organization_name }}
          </td>
        </tr>
        <tr>
          <td style="padding:32px; font-family:Arial, Helvetica, sans-serif; font-size:16px; line-height:24px; color:#1f2937;">
            <h1 style="margin:0 0 24px; font-size:22px; line-height:30px; font-weight:bold; color:#111827;">Invitation à rejoindre {{ site_name }}</h1>
            <p style="margin:0 0 16px;">{% if invitee_name %}Bonjour {{ invitee_name }},{% else %}Bonjour,{% endif %}</p>
            <p style="margin:0 0 24px;">{{ organization_name }} vous invite à créer un compte sur le service en ligne <strong>{{ site_name }}</strong>.</p>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px;">
              <tr>
                <td align="center" style="border-radius:6px; background-color:#1d4ed8;">
                  <a href="{{ signin_url }}" style="display:inline-block; padding:14px 28px; font-family:Arial, Helvetica, sans-serif; font-size:16px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;">Créer mon compte</a>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 16px;">Sur la page de connexion, cliquez sur «&nbsp;Se connecter avec Google&nbsp;» en utilisant l’adresse suivante&nbsp;: <strong>{{ invitee_email }}</strong></p>
            <p style="margin:0 0 24px;">Après authentification, votre compte sur {{ site_name }} sera créé automatiquement. Vous pourrez utiliser nos services et créer votre entrée dans l’annuaire de l’organisation.</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px; background-color:#f9fafb; border:1px solid #e5e7eb; border-radius:6px;">
              <tr>
                <td style="padding:16px 20px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#374151;">
                  <p style="margin:0 0 8px; font-weight:bold; color:#111827;">Vous n’avez pas de compte Google&nbsp;?</p>
                  <p style="margin:0 0 8px;">Vous pouvez en créer un gratuitement en moins d’une minute. Il n’est pas nécessaire de créer une adresse Gmail&nbsp;: votre adresse habituelle <strong>{{ invitee_email }}</strong> suffit.</p>
                  <p style="margin:0;">Lors de l’étape «&nbsp;Méthode de connexion au compte&nbsp;», ne remplissez pas le champ «&nbsp;Nom d’utilisateur …@gmail.com&nbsp;»&nbsp;: cliquez sur «&nbsp;Utiliser l’adresse email existante&nbsp;».</p>
                </td>
              </tr>
            </table>
            <p style="margin:0; font-size:14px; line-height:22px; color:#6b7280;">Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur&nbsp;:<br><a href="{{ signin_url }}" style="color:#1d4ed8; word-break:break-all;">{{ signin_url }}</a></p>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px; border-top:1px solid #e5e7eb; font-family:Arial, Helvetica, sans-serif; font-size:13px; line-height:20px; color:#6b7280;">
            <p style="margin:0 0 8px;">En cas de problème, <a href="{{ contact_url }}" style="color:#1d4ed8;">contactez-nous</a>.</p>
            <p style="margin:0;">Si vous souhaitez utiliser une autre adresse électronique pour vous connecter à notre service, contactez-nous et nous vous enverrons une nouvelle invitation.</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
""",
)
