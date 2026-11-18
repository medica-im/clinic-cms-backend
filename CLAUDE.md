# Project Context

This is the **backend** of a wider clinic CMS project.

## Repositories

- **Backend** (this repo): https://github.com/medica-im/clinic-cms-backend
  - Active code is on the `production` branch; `main` is stale.
  - production server is Debian GNU/Linux 12 (bookworm)
- **Frontend**: https://github.com/medica-im/skcms
  - Relative path from this directory: `../skcms`

## neo4j
* Due to many bugs (default import of the synchronous version of a neomodel model definition instead of the asynchronous one) with the version of neomodel used in this project, it is preferable to use cypher requests with adb (asynchronous) or db (synchronous).

## Outgoing email

Every Mailgun send resolves its identity through `mailer.config.get_sender(organization)`.
It returns the organization's own credentials when it has an active, fully
filled `mailer.MailgunAccount` row, and the `.env` credentials otherwise.

* **Never call `requests.post` against Mailgun directly, and never read
  `settings.MAILGUN_*` at a call site.** Go through `mailer.main`, passing a
  `sender`. A call site that skips the resolver silently sends one
  organization's mail from another's address -- the bug this replaced.
* **Celery tasks take an `organization_id`, not a `SenderConfig`.** The
  dataclass is not JSON-serialisable, and resolving inside the worker picks up
  a credential change made between queueing and sending.
* **A half-filled account falls back rather than being used.** Posting with a
  blank key fails at Mailgun with a 401, which is much harder to diagnose than
  mail arriving from the default address. See `MailgunAccount.is_usable`.
