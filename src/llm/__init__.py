"""Provider gateway. Stages call this package and nothing vendor-specific."""

from src.llm.gateway import GatewayResult, ModelGateway

__all__ = ["GatewayResult", "ModelGateway"]
