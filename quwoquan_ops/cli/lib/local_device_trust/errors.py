"""local_device_trust 包异常类型（逐字搬移）。"""

from __future__ import annotations


class LocalDeviceTrustError(RuntimeError):
    pass


class AndroidSystemTrustUnavailable(LocalDeviceTrustError):
    """The selected Emulator cannot modify its system CA store."""


class AndroidSystemTrustVerificationError(LocalDeviceTrustError):
    """The expected CA is not visible from an Android runtime namespace."""
