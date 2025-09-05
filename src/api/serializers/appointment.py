import logging
from directory.models.graph import Appointment, Office, HouseCall, Entry
from rest_framework import serializers
from neomodel import db

logger=logging.getLogger(__name__)


def update_labels(instance: Appointment|Office|HouseCall, location: str):
    labels= instance.labels()
    if not location and labels==["Appointment"]:
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
    query = f"""MATCH (n:Appointment) WHERE n.uid="{instance.uid}" REMOVE n:Office:HouseCall SET n:Appointment{set} RETURN n;
"""
    logger.debug(query)
    q = db.cypher_query(query, resolve_objects = True)
    logger.debug(q[0][0])
    return q[0][0]

def same_nodes(entry, location, **kwargs):
    if location=='office':
        label=":Office"
    elif location=='house_call':
        label=":HouseCall"
    else:
        label=""
    phone =  f'phone: "{kwargs["phone"]}"' if kwargs["phone"] else ""
    url =  f'url: "{kwargs["url"]}"' if kwargs["url"] else ""
    query = f"""MATCH (:Entry {{uid:"{entry}"}})-[:HAS_APPOINTMENT]->(a:Appointment{label} {{{phone}{url}}}) RETURN a;
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
    entry = serializers.CharField(required=False)
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

    def update(self, instance: Appointment|Office|HouseCall, validated_data):
        location = validated_data["location"]
        url = validated_data["url"]
        phone = validated_data["phone"]
        instance.url=url
        instance.phone=phone
        instance.save()
        update_instance = update_labels(instance, location)
        return update_instance

