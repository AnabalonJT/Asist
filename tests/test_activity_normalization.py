"""Tests for activity_type normalization used in goal progress matching.

Regression coverage for the bug where a goal like "caminar todos los días"
was never marked complete because the goal and the logged activity were stored
with mismatched activity_type strings (e.g. goal "walking" vs activity
"caminata"/"walk"/"Walking").
"""
import pytest

from app.services.activity_types import normalize_activity_type


class TestNormalizeActivityType:
    def test_walking_synonyms_all_map_to_walking(self):
        for value in ["walking", "walk", "caminar", "caminata", "caminando", "Walking", "WALK"]:
            assert normalize_activity_type(value) == "walking", value

    def test_running_synonyms(self):
        for value in ["running", "run", "correr", "corri", "trote", "carrera"]:
            assert normalize_activity_type(value) == "running", value

    def test_case_insensitive_and_trimmed(self):
        assert normalize_activity_type("  Caminar  ") == "walking"
        assert normalize_activity_type("GYM") == "gym"

    def test_unknown_type_is_lowercased_not_dropped(self):
        # Unknown activities still normalize by casing/whitespace so a goal and
        # activity that use the same (unknown) word still match each other.
        assert normalize_activity_type("Baile") == "baile"
        assert normalize_activity_type("  Escalada ") == "escalada"

    def test_empty_and_none(self):
        assert normalize_activity_type("") == ""
        assert normalize_activity_type(None) == ""

    def test_goal_and_activity_words_converge(self):
        # The core regression: the word used when creating the goal and the word
        # used when logging the activity must normalize to the same canonical type.
        goal_word = normalize_activity_type("caminar")      # goal: "caminar todos los días"
        activity_word = normalize_activity_type("caminata")  # activity as labeled by the LLM
        assert goal_word == activity_word == "walking"

