from orin_api.target_selection import ExecutionTarget, select_target


def test_auto_prefers_eligible_local_without_cloud_fallback_for_private_data() -> None:
    decision = select_target(requested=ExecutionTarget.AUTO, local_worker_eligible=True,
        user_authorized=True, contains_private_data=True, cloud_provisioned=True, cloud_authorized=True)
    assert decision.selected == ExecutionTarget.LOCAL


def test_auto_does_not_send_private_data_to_cloud_when_local_worker_is_offline() -> None:
    decision = select_target(requested=ExecutionTarget.AUTO, local_worker_eligible=False,
        user_authorized=True, contains_private_data=True, cloud_provisioned=True, cloud_authorized=True)
    assert decision.selected is None
    assert "safe eligible" in decision.reason


def test_cloud_request_fails_until_environment_and_policy_are_ready() -> None:
    decision = select_target(requested=ExecutionTarget.CLOUD, local_worker_eligible=True,
        user_authorized=True, contains_private_data=False)
    assert decision.selected is None


def test_required_capability_residency_and_resource_constraints_are_applied() -> None:
    decision = select_target(requested=ExecutionTarget.AUTO, local_worker_eligible=True,
        user_authorized=True, required_capabilities=frozenset({"filesystem.read"}),
        local_capabilities=frozenset({"system.info.read"}), required_region="eu-west",
        local_region="us-east", local_resources_available=False)
    assert decision.selected is None


def test_unknown_cost_or_latency_cannot_pass_explicit_cloud_limits() -> None:
    decision = select_target(requested=ExecutionTarget.CLOUD, local_worker_eligible=False,
        user_authorized=True, contains_private_data=False, cloud_provisioned=True,
        cloud_authorized=True, max_cost=1.0, cloud_cost_estimate=None,
        max_latency_ms=1000, cloud_latency_ms=None)
    assert decision.selected is None


def test_auto_honors_only_an_eligible_explicit_preference() -> None:
    decision = select_target(requested=ExecutionTarget.AUTO, local_worker_eligible=True,
        user_authorized=True, contains_private_data=False, cloud_provisioned=True,
        cloud_authorized=True, preferred_target=ExecutionTarget.CLOUD)
    assert decision.selected == ExecutionTarget.CLOUD
