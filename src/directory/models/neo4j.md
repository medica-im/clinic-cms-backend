## Copy "cost" properties from LOCATION rel to Entry node
MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector), (entry)-[:HAS_FACILITY]->(facility:Facility), (effector)-[rel:LOCATION]->(facility) SET entry.carte_vitale=rel.carteVitale, entry.payment=rel.payment, entry.third_party_payer=rel.thirdPartyPayment RETURN entry;

## Delete "cost" properties from LOCATION rel
MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector), (entry)-[:HAS_FACILITY]->(facility:Facility), (effector)-[rel:LOCATION]->(facility) SET rel.carteVitale=null, rel.payment=null, rel.thirdPartyPayment=null RETURN rel;

# Delete HAS_CONVENTION relationships, use Entry property named convention instead
MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector), (effector)-[rel:HAS_CONVENTION]->(c:Convention) SET entry.convention=c.name DELETE rel;
