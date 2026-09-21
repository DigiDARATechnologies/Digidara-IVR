"""Small fixed evaluation set; extend only with reviewed production incidents."""

from dataclasses import dataclass

from app.facility.orchestration.routing import FacilityRouter


@dataclass(frozen=True)
class RouteScenario:
    name: str
    message: str
    expected_route: str
    requires_confirmation: bool


ROUTE_SCENARIOS = (
    RouteScenario("knowledge_definition", "What is an AHU?", "knowledge", False),
    RouteScenario("live_temperature", "What is Chiller-01's current temperature?", "live_data", False),
    RouteScenario("multi_source_diagnosis", "Why did Chiller-01 fail?", "diagnosis", False),
    RouteScenario("maintenance_action", "Create a maintenance request for AHU-02.", "action", True),
    RouteScenario("general_conversation", "Hello, what can you help with?", "general", False),
)


def evaluate_safe_fallback() -> list[tuple[RouteScenario, bool]]:
    """Check user-safe behavior when the LLM router is unavailable."""
    router = FacilityRouter(lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    results = []
    for scenario in ROUTE_SCENARIOS:
        decision = router.route(scenario.message)
        results.append((scenario, decision.route == scenario.expected_route and decision.requires_confirmation == scenario.requires_confirmation))
    return results
