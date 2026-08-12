"""Strongly typed, request-driven acceptance test-data control plane.

Production packages must exclude this entire concern.
"""

from .api import (
    BusinessObjectRef,
    CapabilityRef,
    CapabilityRequest,
    OutputRef,
    Provisioned,
    ReceiptRef,
    TestDataSession,
)

__all__ = (
    "BusinessObjectRef",
    "CapabilityRef",
    "CapabilityRequest",
    "OutputRef",
    "Provisioned",
    "ReceiptRef",
    "TestDataSession",
)
