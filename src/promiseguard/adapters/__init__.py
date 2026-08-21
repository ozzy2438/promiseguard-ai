"""Vendor-neutral operational adapter contracts and sandbox implementations."""

from promiseguard.adapters.contracts import (
    ADAPTER_CONTRACT_VERSION,
    CARRIER_CONTRACT,
    OMS_CONTRACT,
    WMS_CONTRACT,
    AdapterContract,
    CarrierAdapter,
    OmsAdapter,
    OperationsPort,
    WmsAdapter,
)
from promiseguard.adapters.errors import (
    ActionExecutionError,
    AdapterAuthError,
    AdapterError,
    AdapterErrorClass,
    AdapterRateLimited,
    AdapterTimeout,
    AmbiguousProviderTimeout,
    MalformedAdapterResponse,
)
from promiseguard.adapters.sandbox import (
    SandboxCarrierAdapter,
    SandboxOmsAdapter,
    SandboxWmsAdapter,
    SimulatedOperationsAdapter,
)

__all__ = [
    "ADAPTER_CONTRACT_VERSION",
    "CARRIER_CONTRACT",
    "OMS_CONTRACT",
    "WMS_CONTRACT",
    "ActionExecutionError",
    "AdapterAuthError",
    "AdapterContract",
    "AdapterError",
    "AdapterErrorClass",
    "AdapterRateLimited",
    "AdapterTimeout",
    "AmbiguousProviderTimeout",
    "CarrierAdapter",
    "MalformedAdapterResponse",
    "OmsAdapter",
    "OperationsPort",
    "SandboxCarrierAdapter",
    "SandboxOmsAdapter",
    "SandboxWmsAdapter",
    "SimulatedOperationsAdapter",
    "WmsAdapter",
]
