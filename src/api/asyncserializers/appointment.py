import logging
from directory.models.agraph import Appointment, Office, HouseCall, Entry
from rest_framework import serializers
from adrf.serializers import Serializer
from neomodel import adb

logger = logging.getLogger(__name__)


async def update_labels(instance: Appointment | Office | HouseCall, location: str):
    labels = await instance.labels()
    if not location and labels == ["Appointment"]:
        return instance
    if location == "office" and "Office" in labels:
        return instance
    if location == "house_call" and "HouseCall" in labels:
        return instance
    if location == 'office':
        set = ":Office"
    elif location == 'house_call':
        set = ":HouseCall"
    else:
        set = ""
    query = """MATCH (n:Appointment) WHERE n.uid=$uid REMOVE n:Office:HouseCall SET n:Appointment{set} RETURN n;
""".replace("{set}", set)
    q = await adb.cypher_query(query, {"uid": instance.uid}, resolve_objects=True)
    logger.debug(q[0][0])
    return q[0][0]


async def same_nodes(entry, location, **kwargs):
    if location == 'office':
        label = ":Office"
    elif location == 'house_call':
        label = ":HouseCall"
    else:
        label = ""
    params = {"entry": entry}
    conditions = []
    if kwargs["phone"]:
        conditions.append("a.phone = $phone")
        params["phone"] = kwargs["phone"]
    if kwargs["url"]:
        conditions.append("a.url = $url")
        params["url"] = kwargs["url"]
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""MATCH (:Entry {{uid:$entry}})-[:HAS_APPOINTMENT]->(a:Appointment{label}){where} RETURN a;
"""
    logger.debug(f"{query=}")
    q = await adb.cypher_query(query, params, resolve_objects=True)
    nodes: list[Appointment] = []
    for row in q[0]:
        logger.debug(f"{row=}")
        (appointment,) = row
        nodes.append(appointment)
    return nodes


async def get_location(node: Appointment | Office | HouseCall) -> str | None:
    labels = await node.labels()
    if 'HouseCall' in labels:
        return 'house_call'
    elif 'Office' in labels:
        return 'office'
    return None


class AppointmentSerializer(Serializer):
    uid = serializers.CharField(required=False)
    entry = serializers.CharField(required=False)
    url = serializers.URLField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True)
    location = serializers.ChoiceField(choices=['office', 'house_call'], allow_null=True)

    async def ato_representation(self, node):
        entry_node = await node.entry.single()
        return {
            'uid': node.uid,
            'entry': entry_node.uid,
            'phone': node.phone,
            'url': node.url,
            'location': await get_location(node),
        }

    async def acreate(self, validated_data):
        location = validated_data["location"]
        entry_uid = validated_data['entry']
        kwargs = {
            'url': validated_data["url"],
            'phone': validated_data["phone"]
        }
        _nodes = await same_nodes(entry_uid, location, **kwargs)
        if _nodes:
            return _nodes[0]
        if location is None:
            a = Appointment(**kwargs)
        elif location == 'office':
            a = Office(**kwargs)
        elif location == 'house_call':
            a = HouseCall(**kwargs)
        await a.save()
        try:
            entry = await Entry.nodes.get(uid=entry_uid)
        except Entry.DoesNotExist:
            raise serializers.ValidationError(f"Entry {entry_uid} not found")
        await entry.appointments.connect(a)
        return a

    async def aupdate(self, instance: Appointment | Office | HouseCall, validated_data):
        location = validated_data["location"]
        url = validated_data["url"]
        phone = validated_data["phone"]
        instance.url = url
        instance.phone = phone
        await instance.save()
        update_instance = await update_labels(instance, location)
        return update_instance
