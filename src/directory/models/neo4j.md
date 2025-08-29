## Copy "cost" properties from LOCATION rel to Entry node
MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector), (entry)-[:HAS_FACILITY]->(facility:Facility), (effector)-[rel:LOCATION]->(facility) SET entry.carte_vitale=rel.carteVitale, entry.payment=rel.payment, entry.third_party_payment=rel.thirdPartyPayment RETURN entry;

## Delete "cost" properties from LOCATION rel
MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector), (entry)-[:HAS_FACILITY]->(facility:Facility), (effector)-[rel:LOCATION]->(facility) SET rel.carteVitale=null, rel.payment=null, rel.thirdPartyPayment=null RETURN rel;