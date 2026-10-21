import logging
from time import time_ns
from types import SimpleNamespace
from uuid import uuid4

from celery import shared_task
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from neomodel import db

from access.active_access import is_member_sync

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
    """Create a spreadsheet's invitations, then send their emails.

    Two steps, in this order: the sending step is the one a resend job runs on
    its own, and a cancel while sending leaves invitations that exist.
    """
    from access.models import BatchInviteeJob

    job = _start_job(self, job_id)
    if job is None:
        return

    created = _create_invitees(job, rows, entry_uid, _resolve_user_uid(user_sub), role)
    if created is None:
        return
    if send_emails and not _send_invitations(job, created, site_domain):
        return

    job.status = BatchInviteeJob.Status.COMPLETED
    job.save(update_fields=["status", "summary"])
    logger.info(
        f"BatchInviteeJob {job.uid} completed: "
        f"{job.successful_count} created, "
        f"{job.failed_count} failed, "
        f"{job.skipped_duplicate_email_count} skipped (dup email), "
        f"{job.skipped_active_user_count} skipped (active user), "
        f"{job.failed_email_count} email failures"
    )


@shared_task(bind=True)
def process_batch_resend(self, job_id: int, invitee_uids: list[str], site_domain: str):
    """Send existing invitations' emails again: the sending step alone.

    One summary row per invitation, in the order chosen, written before the
    first email, so the report lists them all even when the job is cancelled.
    """
    from access.models import BatchInviteeJob

    job = _start_job(self, job_id)
    if job is None:
        return

    invitees = _load_invitees(invitee_uids)
    job.summary = [
        {
            "row": idx + 1,
            "invitee_uid": uid,
            "email": getattr(invitees.get(uid), "email", None),
            "name": getattr(invitees.get(uid), "name", None) or "",
            "status": "resend",
            "message": "",
        }
        for idx, uid in enumerate(invitee_uids)
    ]
    job.save(update_fields=["summary"])

    if not _send_invitations(job, invitee_uids, site_domain):
        return

    job.status = BatchInviteeJob.Status.COMPLETED
    job.save(update_fields=["status", "summary"])
    logger.info(
        f"BatchInviteeJob {job.uid} completed: "
        f"{job.emails_processed} reminders, "
        f"{job.email_skipped_count} skipped, "
        f"{job.failed_email_count} email failures"
    )


def _start_job(task, job_id: int):
    from access.models import BatchInviteeJob

    try:
        job = BatchInviteeJob.objects.get(id=job_id)
    except BatchInviteeJob.DoesNotExist:
        logger.error(f"BatchInviteeJob {job_id} not found")
        return None

    job.celery_task_id = task.request.id or ""
    job.status = BatchInviteeJob.Status.PROCESSING
    job.save(update_fields=["celery_task_id", "status"])
    return job


def _cancelled(job) -> bool:
    from access.models import BatchInviteeJob

    job.refresh_from_db(fields=["status"])
    return job.status == BatchInviteeJob.Status.CANCELLED


def _create_invitees(job, rows: list[dict], entry_uid: str, user_uid: str | None, role: str) -> list[str] | None:
    """The creation step: one summary row per spreadsheet row, no email.

    The uids created, in row order; None when the job was cancelled.
    """
    summary = []
    created = []

    for idx, row in enumerate(rows):
        if idx % 10 == 0 and _cancelled(job):
            job.summary = summary
            job.save(update_fields=["summary"])
            logger.info(f"BatchInviteeJob {job.uid} cancelled at row {idx + 1}")
            return None

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

            if is_member_sync(email, entry_uid):
                row_result["status"] = "skipped_active_user"
                row_result["message"] = f"{email} a déjà accès à ce site."
                job.skipped_active_user_count += 1
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

            created.append(invitee_uid)

        except Exception as e:
            logger.exception(f"Error processing row {row_num}: {e}")
            row_result["status"] = "failed"
            row_result["message"] = f"Erreur: {str(e)}"
            job.failed_count += 1

        summary.append(row_result)
        _update_progress(job, row_num, summary)

    return created


def _send_invitations(job, invitee_uids: list[str], site_domain: str) -> bool:
    """The sending step: each invitation's email, in order, on its summary row.

    An invitation resend_refusal turns down (used, disabled, its previous
    email still on its way) is not sent; its row says why. False when the job
    was cancelled before the end.
    """
    from access.models import BatchInviteeJob
    from mailer.delivery import latest_deliveries, resend_refusal

    job.phase = BatchInviteeJob.Phase.SENDING
    job.emails_total = len(invitee_uids)
    job.emails_processed = 0
    job.save(update_fields=["phase", "emails_total", "emails_processed"])

    invitees = _load_invitees(invitee_uids)
    latest = latest_deliveries(invitee_uids)
    rows = {row["invitee_uid"]: row for row in job.summary if row.get("invitee_uid")}

    for uid in invitee_uids:
        if _cancelled(job):
            logger.info(f"BatchInviteeJob {job.uid} cancelled at email {job.emails_processed + 1}")
            return False

        invitee = invitees.get(uid)
        refusal = "missing" if invitee is None else resend_refusal(invitee, latest.get(uid))
        row_changed = True
        if refusal:
            job.email_skipped_count += 1
            rows[uid]["email_skipped"] = refusal
        elif not _send_notification_email(
            invitee.email, invitee.name or "", site_domain, invitee_uid=uid, batch_job_uid=job.uid,
        ):
            job.failed_email_count += 1
            rows[uid]["email_error"] = True
        else:
            row_changed = False

        job.emails_processed += 1
        fields = ["emails_processed", "failed_email_count", "email_skipped_count"]
        if row_changed:
            fields.append("summary")
        job.save(update_fields=fields)

    return True


def _load_invitees(uids: list[str]) -> dict[str, SimpleNamespace]:
    query = """
    MATCH (i:Invitee) WHERE i.uid IN $uids
    RETURN i.uid, i.email, i.name, i.active, i.redeemedAt
    """
    results, _ = db.cypher_query(query, {"uids": uids})
    return {
        uid: SimpleNamespace(email=email, name=name, active=active, redeemedAt=redeemed_at)
        for uid, email, name, active, redeemed_at in results
    }


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


def _send_notification_email(
    email: str, name: str, site_domain: str, invitee_uid: str | None = None, batch_job_uid=None,
) -> bool:
    """Reuses mailer.main.send_single_email directly (sync, already in Celery).

    True only when the mail service accepted the message: send_single_email
    does not raise, it answers {"error": ...}. With invitee_uid, the attempt
    is recorded (mailer.delivery) so the invitation shows whether it went out,
    and with batch_job_uid it counts in that job's report.
    """
    from django.contrib.sites.models import Site
    from facility.models import Organization
    from mailer import delivery
    from mailer.config import get_sender
    from mailer.main import send_single_email
    from mailer.templating import get_template, invitation_context, render_email

    try:
        site = Site.objects.get(domain=site_domain)
        organization = Organization.objects.get(site=site)
    except (Site.DoesNotExist, Organization.DoesNotExist):
        logger.error(f"Could not find site/organization for domain {site_domain}")
        return False

    # A remembered address (dead, or a refusal of this organization's mail)
    # is not sent to: the batch reports it suppressed, with why. Checked for
    # a tracked invitation, as send_single_email_task does, and before the
    # email is written.
    from mailer import suppression
    blocked = suppression.blocking(email, organization) if invitee_uid else None
    if blocked is not None:
        logger.info(f"Not sending to {email}: {blocked.reason}")
        row = delivery.record_queued(invitee_uid, email, batch_job_uid=batch_job_uid)
        delivery.mark_suppressed(row.id, blocked)
        return False

    template = get_template(organization, "invitation")
    context = invitation_context(organization, site_domain, name, email)
    rendered = render_email(template, context)

    row = delivery.record_queued(invitee_uid, email, batch_job_uid=batch_job_uid) if invitee_uid else None
    try:
        result = send_single_email(
            email, rendered.subject, rendered.text,
            sender=get_sender(organization), html=rendered.html,
            metadata={"delivery_id": row.id} if row is not None else None,
            tags=["invitation"],
        )
    except Exception as e:
        logger.exception(f"Failed to send notification email to {email}: {e}")
        result = {"error": str(e)}
    if row is not None:
        delivery.mark_result(row.id, result)
    return bool((result or {}).get("id"))
