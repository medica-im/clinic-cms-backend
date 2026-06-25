import logging
from django.conf import settings
from directory.utils import find_entry, async_find_entry
from directory.serializers import (
    ConventionSerializer,
    ThirdPartyPayerSerializer,
    display_tag_name,
)
from api.transformers import createEffectorTypeResources
from api.serializers.allentries import AsyncTagSerializer
from api.utils import process, get_directory, ALLOWED_ACCESS
from api.types.fullentry import FullEntry
from fastapi import Request, HTTPException, status
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.auth import normalize_role, RoleType, is_user_in_authorized_list
from directory.models.agraph import Entry as AgraphEntry
from directory.serializers import TagSerializer

logger=logging.getLogger(__name__)

LANGUAGE = settings.LANGUAGE_CODE


class EffectorObj(object):
    def __init__ (
            self,
            label,
            name,
            gender,
            slug,
            uid,
            effector_uid,
            effector_type,
            address,
            phones,
            updatedAt,
            facility,
            emails,
            websites,
            socialnetworks,
            appointments,
            profile,
            convention,
            carte_vitale,
            third_party_payers,
            payment_methods,
            rpps,
            spoken_languages,
            avatar,
            active,
            deactivation_datetime,
            deactivation_reason,
            memberships,
            tags,
            directories,
        ):
        self.label = label
        self.name = name
        self.gender = gender
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.effector_type = effector_type
        self.address = address
        self.phones = phones
        self.updatedAt = updatedAt
        self.facility = facility
        self.emails = emails
        self.websites = websites
        self.socialnetworks = socialnetworks
        self.appointments = appointments
        self.profile = profile
        self.convention = convention
        self.carte_vitale = carte_vitale
        self.third_party_payers = third_party_payers
        self.payment_methods = payment_methods
        self.rpps = rpps
        self.spoken_languages = spoken_languages
        self.avatar = avatar
        self.active = active
        self.deactivation_datetime = deactivation_datetime
        self.deactivation_reason = deactivation_reason
        self.memberships = memberships
        self.tags = tags
        self.directories = directories

def createEffectorRessource(node):
    try:
        uid = node["entry"].uid
    except Exception as e:
        uid = None
    effector_node=node["effector"]
    health_worker=node["health_worker"]
    address=node["address"]
    label = getattr(
        effector_node,
        f'label_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'label_en',
            None
        )
    )
    name = getattr(
        effector_node,
        f'name_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'name_en',
            None
        )
    )
    gender=effector_node.gender
    slug = getattr(
        effector_node,
        f'slug_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'slug_en',
            None
        )
    )
    effector_uid = effector_node.uid
    et = node["effector_type"]
    effector_type_obj = createEffectorTypeResources(et)
    effector_type_obj.label = node["flex_effector_type_label"] or effector_type_obj.label
    effector_type_dict=effector_type_obj.__dict__
    effector_type_dict["labels"]=node["effector_type_labels"]
    phones = node["phones"]
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
            #location.contactUpdatedAt,
        ]
    )
    facility = {
        "uid": node["facility"].uid,
        "slug": node["facility"].slug,
        "name": node["facility"].name,
        "label": node["facility"].label or node["facility"].name
    }
    emails = node["emails"]
    websites = node["websites"]
    socialnetworks = node["socialnetworks"]
    appointments = node["appointments"]
    profile = node["profile"]
    # convention
    convention_db = node["convention"]
    if convention_db:
        serializer = ConventionSerializer(convention_db)
        convention = serializer.data
    else:
        convention = None
    # carte vitale
    try:
        carte_vitale=node["entry"].carte_vitale
    except Exception as e:
        carte_vitale = None
    #third party payer
    logger.debug(f'{node["third_party_payers"]=}')
    serializer = ThirdPartyPayerSerializer(
        node["third_party_payers"],
        many=True
    )
    try:
        third_party_payers = serializer.data or None
    except:
        third_party_payers = None
    # payment_methods (reuse ThirdPartyPayerSerialize)
    serializer = ThirdPartyPayerSerializer(
        node["payment_methods"],
        many=True
    )
    try:
        payment_methods = serializer.data or None
    except:
        payment_methods = None
    try:
        rpps=health_worker.rpps
    except:
        rpps = None
    try:
        spoken_languages=[
            {
                "tag": t,
                "name": display_tag_name(t, LANGUAGE)
            } for t in health_worker.spoken_languages
        ]
    except:
        spoken_languages = None
    avatar=node["avatar"]
    try:
        active=node["entry"].active
    except:
        active=None
    deactivation_datetime=node["entry"].deactivation_datetime
    deactivation_reason=node["entry"].deactivation_reason
    try:
        memberships = [entry.uid for entry in node["memberships"]]
    except:    
        try:
            memberships = [node["memberships"].uid] if node["memberships"] else None
        except:
            memberships = None
    try:
        serializer = TagSerializer(node["tags"], many=True)
        tags = serializer.data or None
    except Exception as e:
        logger.error(e)
        tags = None
    directories = [d.name for d in node["directories"] if d is not None] if node["directories"] else []

    effector = EffectorObj(
        label,
        name,
        gender,
        slug,
        uid,
        effector_uid,
        effector_type_dict,
        address,
        phones,
        updatedAt,
        facility,
        emails,
        websites,
        socialnetworks,
        appointments,
        profile,
        convention,
        carte_vitale,
        third_party_payers,
        payment_methods,
        rpps,
        spoken_languages,
        avatar,
        active,
        deactivation_datetime,
        deactivation_reason,
        memberships,
        tags,
        directories
    )
    return effector

def get_fullentry(uid):
    entry_node = find_entry(uid=uid)
    entry_object = createEffectorRessource(entry_node)
    entry_pydantic = FullEntry.model_validate(entry_object.__dict__)
    return entry_pydantic

async def createFullEntryResource(node) -> dict:
    entry_node = node["entry"]
    effector_node = node["effector"]
    health_worker = node["health_worker"]
    # label, name, slug
    label = getattr(
        effector_node,
        f'label_{LANGUAGE}',
        getattr(effector_node, 'label_en', None)
    )
    name = getattr(
        effector_node,
        f'name_{LANGUAGE}',
        getattr(effector_node, 'name_en', None)
    )
    gender = effector_node.gender
    slug = getattr(
        effector_node,
        f'slug_{LANGUAGE}',
        getattr(effector_node, 'slug_en', None)
    )
    try:
        uid = entry_node.uid
    except Exception:
        uid = None
    effector_uid = effector_node.uid
    # effector type
    et = node["effector_type"]
    effector_type_obj = createEffectorTypeResources(et)
    effector_type_obj.label = node["flex_effector_type_label"] or effector_type_obj.label
    effector_type = effector_type_obj.__dict__
    effector_type["labels"] = node["effector_type_labels"]
    # address
    address = node["address"]
    # phones
    phones = node["phones"]
    # updatedAt
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
        ]
    )
    # facility
    facility = {
        "uid": node["facility"].uid,
        "slug": node["facility"].slug,
        "name": node["facility"].name,
        "label": node["facility"].label or node["facility"].name,
    }
    # pre-fetched contact data
    emails = node["emails"]
    websites = node["websites"]
    socialnetworks = node["socialnetworks"]
    appointments = node["appointments"]
    profile = node["profile"]
    # convention
    convention_db = node["convention"]
    if convention_db:
        serializer = ConventionSerializer(convention_db)
        convention = serializer.data
    else:
        convention = None
    # carte vitale
    try:
        carte_vitale = entry_node.carte_vitale
    except Exception:
        carte_vitale = None
    # third party payers
    serializer = ThirdPartyPayerSerializer(
        node["third_party_payers"],
        many=True,
    )
    try:
        third_party_payers = serializer.data or None
    except Exception:
        third_party_payers = None
    # payment methods
    serializer = ThirdPartyPayerSerializer(
        node["payment_methods"],
        many=True,
    )
    try:
        payment_methods = serializer.data or None
    except Exception:
        payment_methods = None
    # health worker fields
    try:
        rpps = health_worker.rpps
    except Exception:
        rpps = None
    try:
        spoken_languages = [
            {
                "tag": t,
                "name": display_tag_name(t, LANGUAGE),
            } for t in health_worker.spoken_languages
        ]
    except Exception:
        spoken_languages = None
    # avatar
    avatar = node["avatar"]
    # active
    try:
        active = entry_node.active
    except Exception:
        active = None
    deactivation_datetime = entry_node.deactivation_datetime
    deactivation_reason = entry_node.deactivation_reason
    # memberships
    try:
        memberships = [e.uid for e in node["memberships"]]
    except Exception:
        try:
            memberships = [node["memberships"].uid] if node["memberships"] else None
        except Exception:
            memberships = None
    # tags (async)
    tags = None
    try:
        serializer = AsyncTagSerializer(node["tags"], many=True)
        tags = await serializer.adata or None
    except Exception as e:
        logger.error(e)
    # directories
    directories = [d.name for d in node["directories"] if d is not None] if node["directories"] else []

    return {
        "label": label,
        "name": name,
        "gender": gender,
        "slug": slug,
        "entrySlug": entry_node.slug,
        "uid": uid,
        "effector_uid": effector_uid,
        "effector_type": effector_type,
        "address": address,
        "phones": phones,
        "updatedAt": updatedAt,
        "facility": facility,
        "emails": emails,
        "websites": websites,
        "socialnetworks": socialnetworks,
        "appointments": appointments,
        "profile": profile,
        "convention": convention,
        "carte_vitale": carte_vitale,
        "third_party_payers": third_party_payers,
        "payment_methods": payment_methods,
        "rpps": rpps,
        "spoken_languages": spoken_languages,
        "avatar": avatar,
        "active": active,
        "deactivation_datetime": deactivation_datetime,
        "deactivation_reason": deactivation_reason,
        "memberships": memberships,
        "tags": tags,
        "directories": directories,
        "creator": node.get("creator_uids"),
        "owner": node.get("owner_uids"),
        "redeemEmail": entry_node.redeemEmail,
        "access": getattr(entry_node, 'access', 'anonymous'),
    }

async def async_get_fullentry(uid: str, req: Request, jwt)->FullEntry:
    logger.debug(f"{jwt=}")
    directory = await get_directory(req)
    logger.debug(f"{directory=}")
    role = await get_neo4j_role(jwt, directory.site) or "anonymous"
    logger.debug(f"get_neo4j_role: {role=}")
    normalized_role = normalize_neo4j_role(role)
    logger.debug(f"{normalized_role=}")
    entry_node_dct = await async_find_entry(uid=uid)
    try:
        entry: AgraphEntry = entry_node_dct["entry"]
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    # downgrade role if entry doesn't belong to the request's directory
    # superuser can access everything regardless
    if normalized_role != "superuser":
        entry_directories = [d.name for d in entry_node_dct["directories"] if d is not None] if entry_node_dct.get("directories") else []
        if directory.name not in entry_directories:
            normalized_role = "anonymous"
    entry_access = getattr(entry, 'access', 'anonymous')
    allowed = ALLOWED_ACCESS.get(normalized_role)
    if allowed and entry_access not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if entry_node_dct and entry_node_dct["entry"].active == False:
        if normalized_role == "anonymous":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        owners = await entry.owner.all()
        creators = await entry.creator.all()
        users = owners + creators
        user_authorized = await is_user_in_authorized_list(jwt, users)
        logger.debug(f"{user_authorized=}")
        if not user_authorized and not normalized_role in ["administrator", "superuser"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    entry_dct = await createFullEntryResource(entry_node_dct)
    logger.debug(f"{entry_dct=}")
    attributes = ["phones", "emails", "socialnetworks"]
    process(entry_dct, normalized_role, attributes)
    logger.debug(f"{entry_dct=}")
    entry_pydantic = FullEntry.model_validate(entry_dct)
    return entry_pydantic
