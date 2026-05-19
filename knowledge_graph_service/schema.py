"""
This file contains the schema for the knowledge graph
"""

# Each entry defines one enrichable relationship type.
# The LLM will infer the label and explanation for each node pair.

SCHEMA = {

    # ── Commit relationships ───────────────────────────────────────────────
    "Commit_changes_Code": {
        "source":      {"label": "Commit", "id_prop": "hash",      "fetch_props": ["title", "summary", "timestamp"]},
        "target":      {"label": "Code",   "id_prop": "file_path", "fetch_props": ["file_name", "file_type"]},
        "valid_labels": ["MODIFIES", "REFACTORS", "FIXES", "INTRODUCES", "DELETES"],
        "prompt_hint": "Infer how the commit affected the code file based on the commit title and summary.",
    },
    "Commit_changes_Test": {
        "source":      {"label": "Commit", "id_prop": "hash",      "fetch_props": ["title", "summary", "timestamp"]},
        "target":      {"label": "Test",   "id_prop": "file_path", "fetch_props": ["file_name", "test_level", "outcome"]},
        "valid_labels": ["ADDS_TEST", "MODIFIES_TEST", "REMOVES_TEST", "FIXES_TEST"],
        "prompt_hint": "Infer how the commit affected the test file.",
    },
    "Commit_implements_Feature": {
        "source":      {"label": "Commit",  "id_prop": "hash",  "fetch_props": ["title", "summary"]},
        "target":      {"label": "Feature", "id_prop": "title", "fetch_props": ["unit_of_work", "business_value"]},
        "valid_labels": ["IMPLEMENTS", "PARTIALLY_IMPLEMENTS", "COMPLETES"],
        "prompt_hint": "Infer whether the commit fully or partially implements the feature.",
    },
    "Commit_solves_Bug": {
        "source":      {"label": "Commit", "id_prop": "hash",  "fetch_props": ["title", "summary"]},
        "target":      {"label": "Bug",    "id_prop": "title", "fetch_props": ["root_cause", "detected_date", "solved"]},
        "valid_labels": ["SOLVES", "PARTIALLY_FIXES", "WORKAROUNDS"],
        "prompt_hint": "Infer how the commit addresses the bug based on its root cause.",
    },

    # ── Developer relationships ────────────────────────────────────────────
    "Developer_creates_Commit": {
        "source":      {"label": "Developer", "id_prop": "email", "fetch_props": ["name"]},
        "target":      {"label": "Commit",    "id_prop": "hash",  "fetch_props": ["title", "summary", "timestamp"]},
        "valid_labels": ["AUTHORS", "CO_AUTHORS", "REVIEWS"],
        "prompt_hint": "Infer the developer's role in the commit.",
    },
    "Developer_assigned_to_Issue": {
        "source":      {"label": "Developer", "id_prop": "email", "fetch_props": ["name"]},
        "target":      {"label": "Issue",     "id_prop": "title", "fetch_props": ["status", "priority", "summary"]},
        "valid_labels": ["ASSIGNED_TO", "OWNS", "REVIEWING", "SUPPORTING"],
        "prompt_hint": "Infer the developer's responsibility level for the issue.",
    },

    # ── Issue/Feature/Bug relationships ───────────────────────────────────
    "Issue_updates_Issue": {
        "source":      {"label": "Issue", "id_prop": "title", "fetch_props": ["status", "priority", "summary"]},
        "target":      {"label": "Issue", "id_prop": "title", "fetch_props": ["status", "priority", "summary"]},
        "valid_labels": ["BLOCKS", "DUPLICATES", "RELATES_TO", "DEPENDS_ON", "SUPERSEDES"],
        "prompt_hint": "Infer the dependency or relationship type between these two issues.",
    },
    "Feature_relates_to_Feature": {
        "source":      {"label": "Feature", "id_prop": "title", "fetch_props": ["unit_of_work", "business_value"]},
        "target":      {"label": "Feature", "id_prop": "title", "fetch_props": ["unit_of_work", "business_value"]},
        "valid_labels": ["DEPENDS_ON", "EXTENDS", "CONFLICTS_WITH", "RELATES_TO"],
        "prompt_hint": "Infer the functional relationship between two features.",
    },
    "Bug_caused_by_Feature": {
        "source":      {"label": "Bug",     "id_prop": "title", "fetch_props": ["root_cause", "detected_date"]},
        "target":      {"label": "Feature", "id_prop": "title", "fetch_props": ["unit_of_work", "business_value"]},
        "valid_labels": ["CAUSED_BY", "INTRODUCED_BY", "REGRESSED_BY"],
        "prompt_hint": "Infer how the feature introduction led to the bug.",
    },

    # ── Requirement relationships ─────────────────────────────────────────
    "Requirement_relates_to_Requirement": {
        "source":      {"label": "Requirement", "id_prop": "description", "fetch_props": ["priority"]},
        "target":      {"label": "Requirement", "id_prop": "description", "fetch_props": ["priority"]},
        "valid_labels": ["DEPENDS_ON", "CONFLICTS_WITH", "REFINES", "RELATES_TO"],
        "prompt_hint": "Infer how these two requirements interact or depend on each other.",
    },
    "Requirement_realizes_Feature": {
        "source":      {"label": "Requirement", "id_prop": "description", "fetch_props": ["priority"]},
        "target":      {"label": "Feature",     "id_prop": "title",       "fetch_props": ["unit_of_work", "business_value"]},
        "valid_labels": ["REALIZES", "PARTIALLY_REALIZES", "CONTRADICTS"],
        "prompt_hint": "Infer how well the requirement maps to the feature's intent.",
    },

    # ── Test relationships ────────────────────────────────────────────────
    "Test_tests_Code": {
        "source":      {"label": "Test", "id_prop": "file_path", "fetch_props": ["test_level", "outcome"]},
        "target":      {"label": "Code", "id_prop": "file_path", "fetch_props": ["file_name", "file_type"]},
        "valid_labels": ["UNIT_TESTS", "INTEGRATION_TESTS", "ACCEPTANCE_TESTS", "TESTS"],
        "prompt_hint": "Infer the test coverage type for this code file.",
    },
    "NonFunctional_validates_Test": {
        "source":      {"label": "NonFunctional", "id_prop": "description", "fetch_props": ["category", "target_value"]},
        "target":      {"label": "Test",          "id_prop": "file_path",   "fetch_props": ["test_level", "outcome"]},
        "valid_labels": ["VALIDATES", "PARTIALLY_VALIDATES", "FAILS_TO_VALIDATE"],
        "prompt_hint": "Infer whether the test adequately validates the non-functional requirement.",
    },

    # ── Release relationships ─────────────────────────────────────────────
    "Release_includes_Issue": {
        "source":      {"label": "Release", "id_prop": "version", "fetch_props": ["title", "release_date"]},
        "target":      {"label": "Issue",   "id_prop": "title",   "fetch_props": ["status", "priority", "summary"]},
        "valid_labels": ["INCLUDES", "TARGETS", "DEFERS"],
        "prompt_hint": "Infer whether the issue is fully included, targeted, or deferred in this release.",
    },
}