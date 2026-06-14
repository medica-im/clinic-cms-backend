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
