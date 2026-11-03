"""Whether two spellings of a name can be one person.

"Jean-Marc Dupont", "Dupont Jean-Marc" and "J.-M. Dupont" may be the same
person, or three people. Nothing here decides that: it finds the candidates, in
order of how likely they are, so a human or a reviewing tool chooses. A name
alone never proves identity, which is why none of these results is reused
silently (clone's exact-match rule for people stays as it is).

Strength, strongest first:
  same      the same words, in any order, accents and case ignored
  initials  the same words but an initial stands for a full given name
  partial   one spelling has fewer given names ("Jean Dupont", "Jean-Marc Dupont")
"""
import pytest

from api.serializers.clone.detect import compare_names, name_tokens


class TestTokens:
    def test_case_accents_and_punctuation_are_ignored(self):
        assert name_tokens("Éric  Müller-Dupont") == ["eric", "muller", "dupont"]

    def test_a_hyphen_a_dot_and_a_space_all_separate(self):
        assert name_tokens("J.-M. Dupont") == ["j", "m", "dupont"]
        assert name_tokens("Jean Marc Dupont") == name_tokens("Jean-Marc Dupont")

    def test_an_apostrophe_separates(self):
        assert name_tokens("D'Artagnan") == ["d", "artagnan"]


class TestSame:
    @pytest.mark.parametrize("a, b", [
        ("Jean-Marc Dupont", "Dupont Jean-Marc"),
        ("Jean-Marc Dupont", "Jean Marc Dupont"),
        ("Éric Müller", "eric muller"),
        ("Marie Test", "Marie Test"),
        ("J. Dupont", "J. Dupont"),
        ("Dupont", "Dupont"),
    ])
    def test_the_same_words_in_any_order(self, a, b):
        assert compare_names(a, b) == "same"


class TestInitials:
    @pytest.mark.parametrize("a, b", [
        ("Jean-Marc Dupont", "J.-M. Dupont"),
        ("J.-M. Dupont", "Dupont Jean-Marc"),
        ("J. Dupont", "Jean Dupont"),
    ])
    def test_an_initial_stands_for_a_full_given_name(self, a, b):
        assert compare_names(a, b) == "initials"
        assert compare_names(b, a) == "initials"

    def test_an_initial_must_be_the_right_letter(self):
        assert compare_names("J.-M. Dupont", "Jean-Pierre Dupont") is None
        assert compare_names("J. Dupont", "Jacques Martin") is None


class TestPartial:
    def test_a_missing_second_given_name_is_a_candidate(self):
        assert compare_names("Jean Dupont", "Jean-Marc Dupont") == "partial"
        assert compare_names("Jean-Marc Dupont", "Jean Dupont") == "partial"

    def test_a_lone_surname_is_too_weak_to_be_one(self):
        assert compare_names("Dupont", "Jean Dupont") is None

    def test_partial_also_accepts_an_initial(self):
        assert compare_names("J. Dupont", "Jean-Marc Dupont") == "partial"


class TestNotTheSame:
    @pytest.mark.parametrize("a, b", [
        ("Jean-Marc Dupont", "Jean-Pierre Dupont"),
        ("Jean Dupont", "Jean Durand"),
        ("Marie Test", "Jean Test"),
    ])
    def test_different_words_are_different_people(self, a, b):
        assert compare_names(a, b) is None
