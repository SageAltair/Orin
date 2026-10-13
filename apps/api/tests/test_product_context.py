from __future__ import annotations

import json

from orin_api.ai import AIInterpreter, IntentName
from orin_api.product_context import PRODUCT_INVENTORY, needs_product_context, product_context_for_prompt


def test_application_review_references_resolve_to_orin() -> None:
    assert needs_product_context("Act as a designer. Look at this system and audit the UI.", [])
    assert needs_product_context("I mean this Orin system application I'm using here with you.", [])
    assert needs_product_context("Review this application", [])
    assert needs_product_context("Review it now", ["Look at this system and tell me what to improve."])
    assert not needs_product_context("Review the attached system architecture", [])


def test_product_inventory_distinguishes_status_and_inspection_limits() -> None:
    inventory = json.loads(product_context_for_prompt())
    assert inventory["identity"]["name"] == "Orin"
    assert {screen["name"] for screen in inventory["screens"]} >= {"Home", "Projects", "Tasks", "Settings", "Ask Orin drawer"}
    assert any(capability["status"] == "partially implemented" for capability in inventory["capabilities"])
    assert any("live browser/DOM/screenshot access" in boundary for boundary in inventory["boundaries"])
    assert inventory == PRODUCT_INVENTORY


def test_interpreter_discloses_scope_and_structures_evidence_based_audits() -> None:
    class AuditProvider:
        def structured_output(self, **kwargs: object) -> str:
            system = str(kwargs["system"])
            user = str(kwargs["user"])
            assert "never repeat a generic request for the product purpose" in system
            assert "confirmed defect, evidence-based usability concern, or speculative opportunity" in system
            assert "coverage-gaps section" in system
            assert "current_application" in user
            assert "no live browser/DOM/screenshot access" in user
            return json.dumps({"intent": "RESPOND", "confidence": 0.95, "parameters": {
                "response": "## Scope reviewed\n\nOrin's supplied feature inventory; no live screen was available."
            }})

    proposal = AIInterpreter(AuditProvider(), "model").interpret(
        "Review this application", context=json.dumps({"current_application": PRODUCT_INVENTORY})
    )
    assert proposal.intent == IntentName.RESPOND
    assert "no live screen" in (proposal.parameters.response or "")


def test_unrelated_requests_do_not_receive_orin_self_review_context() -> None:
    assert not needs_product_context("Review the library app I'm designing", [])
