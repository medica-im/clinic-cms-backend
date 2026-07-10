"""Deterministic lookups against the NLM MeSH RDF REST API.

API docs: https://id.nlm.nih.gov/mesh/swagger/ui
No API key required.
"""
import sys
import requests

BASE_URL = "https://id.nlm.nih.gov/mesh"


def find_descriptor_by_label(label: str, match: str = "exact") -> list[dict]:
    """Look up MeSH descriptor(s) by label. Returns [{"resource": <uri>, "label": <str>}, ...]."""
    response = requests.get(
        f"{BASE_URL}/lookup/descriptor",
        params={"label": label, "match": match, "limit": 10},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_descriptor(mesh_id: str) -> dict:
    """Fetch the full JSON-LD record for a descriptor, e.g. mesh_id='D006761'."""
    response = requests.get(f"{BASE_URL}/{mesh_id}.json", timeout=15)
    response.raise_for_status()
    return response.json()


def _label_value(record: dict) -> str | None:
    label = record.get("label")
    return label.get("@value") if isinstance(label, dict) else label


def _tree_numbers(record: dict) -> list[str]:
    tree_numbers = record.get("treeNumber", [])
    if isinstance(tree_numbers, str):
        tree_numbers = [tree_numbers]
    return [tn.rsplit("/", 1)[-1] for tn in tree_numbers]


def resolve_lineage(mesh_id: str) -> list[dict]:
    """Given a descriptor's MeSH Unique ID (e.g. 'D006761'), walk broaderDescriptor
    links up to the root and return the lineage, root-first. Each entry has the
    descriptor's unique_id, label, and tree number(s).
    """
    chain = []
    current_id = mesh_id
    while current_id:
        record = get_descriptor(current_id)
        chain.append({
            "unique_id": record.get("identifier"),
            "label": _label_value(record),
            "tree_numbers": _tree_numbers(record),
        })
        broader = record.get("broaderDescriptor")
        current_id = broader.rsplit("/", 1)[-1] if broader else None
    chain.reverse()
    return chain


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Hospitals"

    matches = find_descriptor_by_label(query)
    if not matches:
        print(f"No descriptor found for label '{query}'")
        sys.exit(1)

    for match in matches:
        mesh_id = match["resource"].rsplit("/", 1)[-1]
        print(f"\n[{match['label']}] Unique ID: {mesh_id}")
        print("  Lineage (root -> leaf):")
        for node in resolve_lineage(mesh_id):
            tree_numbers = ", ".join(node["tree_numbers"]) or "-"
            print(f"    {node['unique_id']:<10} {tree_numbers:<18} {node['label']}")
