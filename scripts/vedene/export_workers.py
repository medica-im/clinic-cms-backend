"""Export one site's organization, facilities and workers from the old backend.

Runs inside the old backend's Django container (branch main, where workers
live in the workforce NetworkNode/NetworkEdge graph), and only reads:

    docker exec -i -e EXPORT_SITE=old.dev.msp-vedene.fr vedene-django-1 \
        python manage.py shell < scripts/vedene/export_workers.py \
        | sed -n '/^-----BEGIN EXPORT-----$/,/^-----END EXPORT-----$/p' \
        | sed '1d;$d' > vedene.json

Keeps the old data's own shape; mapping it onto the Neo4j model is the
import's job (directory/management/commands/import_entries.py). Every worker
linked to the organization is exported, whatever roles may see it, with those
roles recorded. The JSON is printed between marker lines because log output
shares stdout.
"""
import json
import os

from django.contrib.sites.models import Site
from django.forms.models import model_to_dict

from directory.models import Slug
from facility.models import Facility, LegalEntity, Organization
from workforce.models import (
    ADELI,
    RPPS,
    CarteVitale,
    Conventionnement,
    Label,
    NetworkEdge,
    NetworkNode,
    NodeSet,
    Payment,
    SpokenLanguage,
    ThirdPartyPayment,
    WorkforceNetworkedgeFacilities,
    WorkforceNetworkedgeOrganizations,
)


def names(qs):
    return sorted(o.name for o in qs.all())


def visibility(obj):
    return {
        "roles": names(obj.roles),
        "public_visible": obj.public_visible,
        "contact_visible": obj.contact_visible,
    }


def mesh(node):
    if node.mesh is None:
        return None
    return {"uid": node.mesh.uid, "fr": node.mesh.fr, "en": node.mesh.en}


def contact(c, organization):
    if c is None:
        return None
    image = c.profile_image.name if c.profile_image else None
    return {
        "id": c.id,
        "person_type": c.person_type,
        "formatted_name": c.formatted_name,
        "formatted_name_definite_article": c.formatted_name_definite_article,
        "first_name": c.first_name,
        "middle_name": c.middle_name,
        "last_name": c.last_name,
        "title": c.title,
        "url": c.url,
        "blurb": c.blurb,
        "profile_image": image,
        "addresses": [
            {
                "type": a.type,
                "street": a.street,
                "city": a.city,
                "state": a.state,
                "zip": a.zip,
                "latitude": str(a.latitude) if a.latitude is not None else None,
                "longitude": str(a.longitude) if a.longitude is not None else None,
                "zoom": a.zoom,
                **visibility(a),
            }
            for a in c.addresses.all()
        ],
        "phones": [
            {"phone": p.phone, "type": p.type,
             "organizations": names(p.organization), **visibility(p)}
            for p in c.phonenumbers.all()
        ],
        "emails": [
            {"email": e.email, "type": e.type,
             "organizations": names(e.organization), **visibility(e)}
            for e in c.emails.all()
        ],
        "websites": [
            {"url": w.website, "type": w.type,
             "organizations": names(w.organization), **visibility(w)}
            for w in c.websites.all()
        ],
        "socialnetworks": [
            {"type": s.type, "handle": s.handle, "url": s.url,
             "organizations": names(s.organization), **visibility(s)}
            for s in c.socialnetworks.all()
        ],
        "profiles": [
            {"text": p.text, "roles": names(p.roles)}
            for p in c.profiles.filter(organization=organization)
        ],
        "appointments": [
            {
                "url": a.url,
                "phone": a.phone,
                "app": a.app.name if a.app else None,
                "roles": names(a.roles),
                "organizations": names(a.organization),
            }
            for a in c.appointments.all()
        ],
    }


def edge_scope(edge, organization):
    """Roles that see this edge in the organization, and its facilities."""
    try:
        roles = names(WorkforceNetworkedgeOrganizations.objects.get(
            networkedge=edge, organization=organization
        ).roles)
    except WorkforceNetworkedgeOrganizations.DoesNotExist:
        roles = []
    facilities = sorted(
        WorkforceNetworkedgeFacilities.objects
        .filter(networkedge=edge, facility__organization=organization)
        .values_list("facility__name", flat=True)
    )
    return roles, facilities


def occupations(node, organization, gender):
    occupation = NodeSet.objects.get(name="occupation")
    specialty = NodeSet.objects.get(name="medical_specialty")
    out = []
    for occ in node.ancestors().filter(node_set=occupation):
        item = {
            "name": occ.name,
            "label_fr": Label.get_label(occ.name, gender, "S", "fr"),
            "mesh": mesh(occ),
            "specialty": None,
            "edges": [],
        }
        for edge in NetworkEdge.objects.path(start_node=occ, end_node=node):
            if organization not in edge.organizations.all():
                continue
            roles, facilities = edge_scope(edge, organization)
            item["edges"].append({
                "parent": edge.parent.name,
                "child": edge.child.name,
                "roles": roles,
                "facilities": facilities,
            })
            if edge.parent.node_set == specialty:
                item["specialty"] = {
                    "name": edge.parent.name,
                    "label_fr": Label.get_label(edge.parent.name, gender, "S", "fr"),
                    "mesh": mesh(edge.parent),
                }
        out.append(item)
    return out


def worker(node, organization, site):
    user = node.user
    gender = user.grammatical_gender.name if user.grammatical_gender else None
    rpps = RPPS.objects.filter(node=node).first()
    adeli = ADELI.objects.filter(node=node).first()
    vitale = CarteVitale.objects.filter(node=node, organization=organization).first()
    convention = Conventionnement.objects.filter(node=node, organization=organization).first()
    payment = Payment.objects.filter(node=node, organization=organization).first()
    languages = SpokenLanguage.objects.filter(node=node).first()
    slug = Slug.objects.filter(user=user, site=site).first()
    parent_edges = NetworkEdge.objects.filter(child=node, organizations=organization)
    return {
        "node": {"id": node.id, "name": node.name, "label": node.label},
        "user": {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "grammatical_gender": gender,
        },
        "visible_to": sorted({r for e in parent_edges for r in edge_scope(e, organization)[0]}),
        "slug": slug.slug if slug else None,
        "contact": contact(getattr(user, "contact", None), organization),
        "occupations": occupations(node, organization, gender or "masculine"),
        "rpps": rpps.identifier if rpps else None,
        "adeli": adeli.identifier if adeli else None,
        "carte_vitale": vitale.is_accepted if vitale else None,
        "convention": convention.convention.name if convention else None,
        "payment": names(payment.method) if payment else [],
        "third_party_payer": sorted(
            t.payer.name
            for t in ThirdPartyPayment.objects.filter(
                node=node, organization=organization, available=True
            )
        ),
        "spoken_languages": list(languages.tags) if languages else [],
    }


def organization_fields(organization):
    """Its own text fields, translations included (formatted_name_fr, ...)."""
    keep = (
        "name", "company_name", "formatted_name", "formatted_name_definite_article",
        "website_title", "website_description", "google_site_verification", "language",
    )
    return {
        k: v for k, v in model_to_dict(organization).items()
        if k.startswith(keep) and isinstance(v, (str, type(None)))
    }


def export(domain):
    site = Site.objects.get(domain=domain)
    organization = Organization.objects.get(site=site)
    user_set = NodeSet.objects.get(name="user")
    child_ids = (
        NetworkEdge.objects
        .filter(organizations=organization)
        .values_list("child_id", flat=True)
    )
    nodes = NetworkNode.objects.filter(node_set=user_set, id__in=child_ids).order_by("name")
    return {
        "source": {"site": domain},
        "organization": {
            **organization_fields(organization),
            "city": organization.city.name if organization.city else None,
            "category": organization.category.name if organization.category else None,
            "contact": contact(organization.contact, organization),
            "legal_entities": [
                {k: v for k, v in model_to_dict(le).items() if k not in ("id", "organization")}
                for le in LegalEntity.objects.filter(organization=organization)
            ],
        },
        "facilities": [
            {
                "name": f.name,
                "active": f.active,
                "contact": contact(f.contact, organization),
            }
            for f in Facility.objects.filter(organization=organization).order_by("name")
        ],
        "workers": [worker(n, organization, site) for n in nodes],
    }


data = export(os.environ["EXPORT_SITE"])
print("-----BEGIN EXPORT-----")
print(json.dumps(data, ensure_ascii=False, indent=2))
print("-----END EXPORT-----")
