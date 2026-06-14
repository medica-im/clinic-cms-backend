import logging
from time import time_ns
from uuid import uuid4

from celery import shared_task
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from neomodel import db

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_batch_invitees(
    self,
    job_id: int,
    rows: list[dict],
    entry_uid: str,
    user_sub: str,
    role: str,
    send_emails: bool,
    site_domain: str,
):
    from access.models import BatchInviteeJob

    try:
        job = BatchInviteeJob.objects.get(id=job_id)
    except BatchInviteeJob.DoesNotExist:
        logger.error(f"BatchInviteeJob {job_id} not found")
        return

    job.celery_task_id = self.request.id or ""
    job.status = BatchInviteeJob.Status.PROCESSING
    job.save(update_fields=["celery_task_id", "status"])

    user_uid = _resolve_user_uid(user_sub)
    summary = []

    for idx, row in enumerate(rows):
        if idx % 10 == 0:
            job.refresh_from_db(fields=["status"])
            if job.status == BatchInviteeJob.Status.CANCELLED:
                job.summary = summary
                job.save(update_fields=["summary"])
                logger.info(f"BatchInviteeJob {job.uid} cancelled at row {idx + 1}")
                return

        email = (row.get("email") or "").strip().lower()
        name = (row.get("name") or "").strip()
        row_num = idx + 1
        row_result = {
            "row": row_num,
            "name": name,
            "email": email,
            "status": None,
            "message": "",
            "invitee_uid": None,
            "existing_invitee_uid": None,
        }

        try:
            try:
                validate_email(email)
            except ValidationError:
                row_result["status"] = "failed"
                row_result["message"] = f"Adresse email invalide: {email}"
                job.failed_count += 1
                summary.append(row_result)
                _update_progress(job, row_num, summary)
                continue

            dup_uid = _check_duplicate_email(entry_uid, email)
            if dup_uid:
                row_result["status"] = "skipped_duplicate_email"
                row_result["message"] = f"Une invitation pour {email} existe déjà."
                row_result["existing_invitee_uid"] = dup_uid
                job.skipped_duplicate_email_count += 1
                summary.append(row_result)
                _update_progress(job, row_num, summary)
                continue

            if name:
                redeemed_uid = _check_redeemed_invitee_by_name(entry_uid, name)
                if redeemed_uid:
                    row_result["status"] = "skipped_active_user"
                    row_result["message"] = (
                        f"Un utilisateur actif avec le nom '{name}' existe déjà."
                    )
                    row_result["existing_invitee_uid"] = redeemed_uid
                    job.skipped_active_user_count += 1
                    summary.append(row_result)
                    _update_progress(job, row_num, summary)
                    continue

            invitee_uid = _create_invitee_node(
                email=email,
                name=name,
                role=role,
                entry_uid=entry_uid,
                user_uid=user_uid,
            )

            row_result["status"] = "created"
            row_result["message"] = "Invitation créée avec succès."
            row_result["invitee_uid"] = invitee_uid
            job.successful_count += 1

            if name:
                unredeemed_uid = _check_unredeemed_invitee_by_name(
                    entry_uid, name, invitee_uid
                )
                if unredeemed_uid:
                    row_result["status"] = "warning_name_match"
                    row_result["message"] = (
                        f"Invitation créée, mais une invitation non utilisée "
                        f"pour '{name}' existe déjà."
                    )
                    row_result["existing_invitee_uid"] = unredeemed_uid

            if send_emails:
                email_ok = _send_notification_email(email, name, site_domain)
                if not email_ok:
                    job.failed_email_count += 1
                    row_result["email_error"] = True

        except Exception as e:
            logger.exception(f"Error processing row {row_num}: {e}")
            row_result["status"] = "failed"
            row_result["message"] = f"Erreur: {str(e)}"
            job.failed_count += 1

        summary.append(row_result)
        _update_progress(job, row_num, summary)

    job.status = BatchInviteeJob.Status.COMPLETED
    job.summary = summary
    job.save(update_fields=["status", "summary"])
    logger.info(
        f"BatchInviteeJob {job.uid} completed: "
        f"{job.successful_count} created, "
        f"{job.failed_count} failed, "
        f"{job.skipped_duplicate_email_count} skipped (dup email), "
        f"{job.skipped_active_user_count} skipped (active user), "
        f"{job.failed_email_count} email failures"
    )


def _resolve_user_uid(sub: str) -> str | None:
    """Sync equivalent of the async user lookup in invitees.py:193-201."""
    query = """
    MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
    RETURN u.uid AS uid
    """
    results, _ = db.cypher_query(query, {"sub": sub})
    if results:
        return results[0][0]
    return None


def _check_duplicate_email(entry_uid: str, email: str) -> str | None:
    """Sync equivalent of the duplicate check in invitees.py:142-149."""
    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
    WHERE toLower(invitee.email) = toLower($email)
    RETURN invitee.uid AS uid
    """
    results, _ = db.cypher_query(query, {"entry_uid": entry_uid, "email": email})
    if results:
        return results[0][0]
    return None


def _check_redeemed_invitee_by_name(entry_uid: str, name: str) -> str | None:
    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
    WHERE toLower(invitee.name) = toLower($name)
      AND invitee.redeemedAt IS NOT NULL
    RETURN invitee.uid AS uid
    """
    results, _ = db.cypher_query(query, {"entry_uid": entry_uid, "name": name})
    if results:
        return results[0][0]
    return None


def _check_unredeemed_invitee_by_name(
    entry_uid: str, name: str, exclude_uid: str
) -> str | None:
    query = """
    MATCH (entry:Entry {uid: $entry_uid})<-[:INVITED_TO]-(invitee:Invitee)
    WHERE toLower(invitee.name) = toLower($name)
      AND invitee.redeemedAt IS NULL
      AND invitee.uid <> $exclude_uid
    RETURN invitee.uid AS uid
    """
    results, _ = db.cypher_query(
        query,
        {"entry_uid": entry_uid, "name": name, "exclude_uid": exclude_uid},
    )
    if results:
        return results[0][0]
    return None


def _create_invitee_node(
    email: str,
    name: str,
    role: str,
    entry_uid: str,
    user_uid: str | None,
) -> str:
    """Sync equivalent of invitee creation in invitees.py:175-206."""
    now = time_ns() // 1_000_000
    invitee_uid = uuid4().hex

    if user_uid:
        query = """
        MATCH (entry:Entry {uid: $entry_uid})
        MATCH (user:User {uid: $user_uid})
        CREATE (invitee:Invitee {
            uid: $invitee_uid,
            email: $email,
            name: $name,
            role: $role,
            active: true,
            createdAt: $now
        })
        CREATE (invitee)-[:INVITED_TO]->(entry)
        CREATE (invitee)-[:CREATED_BY]->(user)
        RETURN invitee.uid AS uid
        """
        params = {
            "entry_uid": entry_uid,
            "user_uid": user_uid,
            "invitee_uid": invitee_uid,
            "email": email,
            "name": name,
            "role": role,
            "now": now,
        }
    else:
        query = """
        MATCH (entry:Entry {uid: $entry_uid})
        CREATE (invitee:Invitee {
            uid: $invitee_uid,
            email: $email,
            name: $name,
            role: $role,
            active: true,
            createdAt: $now
        })
        CREATE (invitee)-[:INVITED_TO]->(entry)
        RETURN invitee.uid AS uid
        """
        params = {
            "entry_uid": entry_uid,
            "invitee_uid": invitee_uid,
            "email": email,
            "name": name,
            "role": role,
            "now": now,
        }

    results, _ = db.cypher_query(query, params)
    if not results:
        raise RuntimeError(f"Failed to create Invitee node for {email}")
    return results[0][0]


def _update_progress(job, processed_rows: int, summary: list):
    job.processed_rows = processed_rows
    job.summary = summary
    job.save(update_fields=[
        "processed_rows",
        "successful_count",
        "failed_count",
        "skipped_duplicate_email_count",
        "skipped_active_user_count",
        "failed_email_count",
        "summary",
    ])


def _send_notification_email(email: str, name: str, site_domain: str) -> bool:
    """Reuses mailer.main.send_single_email directly (sync, already in Celery)."""
    from django.contrib.sites.models import Site
    from facility.models import Organization
    from mailer.main import send_single_email

    try:
        site = Site.objects.get(domain=site_domain)
        organization = Organization.objects.get(site=site)
    except (Site.DoesNotExist, Organization.DoesNotExist):
        logger.error(f"Could not find site/organization for domain {site_domain}")
        return False

    subject = (
        f"{organization.formatted_name} vous invite à utiliser "
        f"le service {site_domain}"
    )
    message = (
        f"Bonjour {name if name else ''}!\n\n"
        f"{organization.formatted_name} vous invite à créer un compte sur le "
        f"service en ligne {site_domain}. Vous pouvez vous rendre à l'adresse "
        f"suivante:\n\n"
        f"https://{site_domain}/signin\n\n"
        f"et cliquer sur \"Se connecter avec Google\". Vous devez utiliser "
        f"l'adresse mail suivante: {email} Si vous n'avez pas de compte Google "
        f"lié à cette adresse, vous pourrez en créer un gratuitement en moins "
        f"d'une minute. Il n'est pas nécessaire de créer une adresse Gmail! "
        f"Votre mail habituel {email} est suffisant.\n\n"
        f"Si vous devez créer un compte Google, lors de l'étape "
        f"\"Méthode de connexion au compte\", ne remplissez pas le champ "
        f"\"Nom d'utilisateur  ...@gmail.com\". Cliquez sur "
        f"\"Utiliser l'adresse email existante\".\n\n"
        f"Après authentification par le service \"Se connecter avec Google\", "
        f"votre compte sur {site_domain} sera créé automatiquement. Vous "
        f"pourrez utiliser nos services et créer votre entrée dans l'annuaire "
        f"de l'organisation.\n\n"
        f"En cas de problème, merci de nous contacter via "
        f"https://{site_domain}/contact\n\n"
        f"Si vous souhaitez utiliser une autre adresse électronique pour vous "
        f"connecter à notre service, contactez-nous et nous vous enverrons "
        f"une nouvelle invitation."
    )

    try:
        send_single_email(email, subject, message)
        return True
    except Exception as e:
        logger.exception(f"Failed to send notification email to {email}: {e}")
        return False
