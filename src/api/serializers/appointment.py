import logging
from directory.models.graph import Appointment, Office, HouseCall, Entry
from rest_framework import serializers
from neomodel import db

logger=logging.getLogger(__name__)


def same_nodes(entry, location, **kwargs):
    if location=='office':
        label=":Office"
    elif location=='house_call':
        label=":HouseCall"
    else:
        label=""
    phone =  f'phone="{kwargs["phone"]}' if kwargs["phone"] else ""
    url =  f'url="{kwargs["url"]}' if kwargs["url"] else ""
    query = f"""MATCH (:Entry{label} {{uid="{entry}"}})-[:HAS_APPOINTMENT]->(a:Appointment {{{phone}{url}}}) RETURN a;
"""
    logger.debug(f"{query=}")
    q = db.cypher_query(query, resolve_objects = True)
    nodes: list[Appointment]=[]
    for row in q[0]:
        logger.debug(f"{row=}")
        (
          appointment,
        ) = row
        nodes.append(appointment)
    return nodes

class AppointmentSerializer(serializers.Serializer):
    uid = serializers.CharField(required=False)
    entry = serializers.CharField()
    url = serializers.URLField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True)
    location = serializers.ChoiceField(choices=['office', 'house_call'], allow_null=True)

    def create(self, validated_data):
        location = validated_data["location"]
        entry_uid = validated_data['entry']
        kwargs = {
            'url': validated_data["url"],
            'phone': validated_data["phone"]
        }
        _nodes = same_nodes(entry_uid, location, **kwargs)
        if _nodes:
            return _nodes[0]
        if  location is None:
            a = Appointment(**kwargs)
        elif location == 'office':
            a = Office(**kwargs)
        elif location == 'house_call':
            a = HouseCall(**kwargs)
        a.save()
        try:
            entry = Entry.nodes.get(uid=entry_uid)
        except Exception as e:
            logger.error(e)
            raise serializers.ValidationError(f"Entry {entry_uid} not found")
        entry.appointments.connect(a)
        return a