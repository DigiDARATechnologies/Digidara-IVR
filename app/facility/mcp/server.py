"""MCP server factory for authenticated Facility Operations tool access.

The caller's organization is bound when this server is built. Tool callers
cannot supply an organization identifier, preventing cross-tenant selection by
an LLM or an MCP host.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer

from app.facility.application.facility_tools import FacilityToolService
from app.facility.application.service_request_actions import FacilityActionService
from app.facility.infrastructure.repository import FacilityRepository


def build_facility_mcp_server(
    repository: FacilityRepository, organization_id: int, actor_user_id: int | None = None,
) -> MCPServer:
    tools = FacilityToolService(repository, organization_id)
    server = MCPServer(
        name="nectar-facility-operations",
        version="0.1.0",
        instructions=(
            "Use read tools to gather facility evidence. Never infer a measurement "
            "that a tool did not return. A service request requires a single-use "
            "confirmation created by the authenticated application before it can run."
        ),
    )

    @server.tool(description="Get the facility record, location, type, status, and configured metadata for one asset.")
    def get_asset_details(asset_code: str) -> dict[str, Any]:
        return tools.get_asset_details(asset_code)

    @server.tool(description="Get the current operational status of one facility asset.")
    def get_asset_status(asset_code: str) -> dict[str, Any]:
        return tools.get_asset_status(asset_code)

    @server.tool(description="Get recent live sensor readings for an asset, optionally filtered to one metric.")
    def get_sensor_data(asset_code: str, metric: str | None = None) -> dict[str, Any]:
        return tools.get_sensor_data(asset_code, metric)

    @server.tool(description="Get the most recent power measurement and configured normal baseline for an asset.")
    def get_energy_consumption(asset_code: str) -> dict[str, Any]:
        return tools.get_energy_consumption(asset_code)

    @server.tool(description="Get active and acknowledged alerts, optionally limited to one asset.")
    def get_active_alerts(asset_code: str | None = None) -> dict[str, Any]:
        return tools.get_active_alerts(asset_code)

    @server.tool(description="Get configured dependency relationships between HVAC or facility assets.")
    def get_asset_relationships(asset_code: str) -> dict[str, Any]:
        return tools.get_asset_relationships(asset_code)

    if actor_user_id is not None:
        actions = FacilityActionService(repository, organization_id, actor_user_id)

        @server.tool(description="Create exactly one service request from an already confirmed, single-use confirmation ID.")
        def create_service_request(confirmation_id: str) -> dict[str, Any]:
            return actions.confirm_and_create_service_request(confirmation_id)

    return server
