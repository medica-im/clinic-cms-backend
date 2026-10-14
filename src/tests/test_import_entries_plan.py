"""What import_entries plans to write, from an old-stack export.

The plan is the part of the import that decides: which effector type each old
occupation becomes, how many entries a person gets, at which facility, which
entry inherits the old public slug, and whether it is shown. Reading the
graph and writing it come after, and are found-or-created by natural keys.
"""
from directory.management.commands.import_entries import plan_entries


def worker(occupations, visible_to=("anonymous", "superuser"), slug="jeanne-dupont"):
    return {
        "node": {"name": "jeanne.dupont@example.org"},
        "contact": {"formatted_name": "Jeanne  Dupont"},
        "visible_to": list(visible_to),
        "slug": slug,
        "occupations": occupations,
    }


def occupation(name, facilities=("cabinet",), specialty=None):
    return {
        "name": name,
        "specialty": {"name": specialty} if specialty else None,
        "edges": [{"facilities": list(facilities)}],
    }


def plan(*workers):
    return plan_entries({"workers": list(workers)}, main_facility="msp")


def test_the_specialty_decides_the_type():
    planned, problems = plan(worker([occupation("physician", specialty="general_practitioner")]))
    assert problems == []
    assert [p.type_slug for p in planned] == ["medecin-generaliste"]


def test_a_role_comes_after_the_occupation_and_gets_neither_slug_nor_billing():
    planned, _ = plan(worker([
        occupation("governing_board", facilities=()),
        occupation("physical_therapist"),
    ]))
    assert [(p.type_slug, p.old_slug, p.secondary) for p in planned] == [
        ("kinesitherapeute", "jeanne-dupont", False),
        ("gerant", None, True),
    ]


def test_two_occupations_keep_their_old_order():
    planned, _ = plan(worker([occupation("physical_therapist"), occupation("osteopathic_manual_practitioner")]))
    assert [p.type_slug for p in planned] == ["kinesitherapeute", "osteopathe"]
    assert planned[0].old_slug == "jeanne-dupont"


def test_no_facility_means_the_main_one():
    planned, _ = plan(worker([occupation("governing_board", facilities=())]))
    assert planned[0].facility == "msp"


def test_one_entry_per_facility():
    planned, _ = plan(worker([occupation("pharmacist", facilities=("ventoux", "magistrale"))]))
    assert sorted(p.facility for p in planned) == ["magistrale", "ventoux"]


def test_hidden_from_the_public_means_inactive():
    planned, _ = plan(worker([occupation("pharmacist")], visible_to=("superuser",)))
    assert planned[0].active is False


def test_an_unmapped_occupation_is_a_problem_not_a_guess():
    planned, problems = plan(worker([occupation("astrologer")]))
    assert planned == []
    assert problems == ["Jeanne Dupont: no effector type for occupation 'astrologer'"]
