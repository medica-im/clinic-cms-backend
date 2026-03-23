[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

# Clinic CMS

Content Management System for health centers, outpatient clinics, private medical practices and healthcare organizations.

This repository contains the Python backend code of Clinic CMS.

You can find a library regrouping frontend components of Clinic CMS at https://github.com/medica-im/sklib

Examples of frontends:
* Outpatient clinic: https://github.com/medica-im/skcms
* Addressbook of healthcare organizations and health professionals: https://github.com/medica-im/addressbook 

The idea behind this framework is to put the biggest amount of data in the database and automate the rendering. For instance, if you add a new healthcare professional in the database, all related components (addressbook, healthcare workers count, list of medical specialties available) will be automatically updated. Likewise if you add a new facility to your organization or if you modify an existing one. Thanks to our Svelte components and reactive store variables, all the pages of your website are always up-to-date.

The CMS can power one or multiple website(s).

It is divided into a single backend server (which can host the data for one or more websites) and one frontend node server for each website.

Backend (server) and frontend (clients) communicate through REST API calls only.

We are using nginx to dispatch requests to the backend (gunicorn for the legacy API v1 endpoints run by Django Rest Framework or FastAPI for the new v2 API endpoints) or to the frontend (node server running Sveltekit).

The frontend is a SvelteKit SSR rendered app / website. It gives you the best of the classic multi-page website world (immediate rendering on first page visit, search engine referencement) and the best of the pure JavaScript app world (advanced, fast web apps). We plan to add PWA support.

## Backend
* Django
* Django Rest Framework
* gunicorn
* FastAPI
* neo4j

We believe healthcare organizations are first and foremost social networks. The graph database running our social networks is neo4j. The legacy database for tabular data is Postgres. 

## Backup

### neo4j

```
docker exec backend-neo4j-1 bin/neo4j-admin backup --database=neo4j --backup-dir=/backup
```

#### apoc triggers

// Add a timestamp on every node created:
CALL apoc.trigger.add('create-timestamp','UNWIND $createdNodes AS node
SET node.updatedAt = timestamp()', {phase:'before'});

// Add a timestamp on every node updated (property added/updated):
CALL apoc.trigger.add('update-insert-timestamp', 'UNWIND keys($assignedNodeProperties) as key
UNWIND apoc.trigger.propertiesByKey($assignedNodeProperties, key) as update
WITH update.node as node
SET node.updatedAt = timestamp()', {phase:'before'});

//Add a timestamp on every node updated (property removed):
CALL apoc.trigger.add('update-remove-timestamp', 'UNWIND keys($removedNodeProperties) as key
UNWIND apoc.trigger.propertiesByKey($removedNodeProperties, key) as update
WITH update.node as node
SET node.updatedAt = timestamp()', {phase:'before'});

We are also making use of django-postgresql-dag (Django & Postgresql-based Directed Acyclic Graphs) to build the workforce graph. Each member of the workforce (healthcare professionals, management, administrative and support staff) is included in a graph based on MeSH with metadata such as location, specialty, organization membership. This graph is used to power the addressbook. It may be replaced in the future by a fully fledged graph database such as neo4j.

## Frontend
* SvelteKit
* [Skeleton UI](https://skeleton.dev): a Svelte UI toolkit based on Tailwind CSS

## Languages
* Code, comments and variables: English only.
* All i18n variables have corresponding English and French strings.

## License
GPL v.3

You are free to use this code to create and sell your own websites but please share bug fixes and improvements with us, as required by the license. This will benefit everyone.