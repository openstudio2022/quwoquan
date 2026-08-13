"""local_environment_auth 包对外数据类型（原单文件 dataclass 逐字搬移）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LocalEnvironmentAuth:
    environment: dict[str, str]
    secret_path: Path


@dataclass(frozen=True)
class LocalAcceptanceSession:
    """Ephemeral bearer session for a local integration environment."""

    owner_id: str
    persona_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)

    def authorization_header(self) -> str:
        return "Bearer " + self.access_token


@dataclass(frozen=True)
class LocalAcceptanceActor:
    """Canonical non-production account created through public auth commands."""

    role: str
    session: LocalAcceptanceSession
    challenge_id: str
    account_state: str
    identity_origin: str


@dataclass(frozen=True)
class LocalEnvironmentHTTPError(RuntimeError):
    """Redacted local-environment HTTP failure with a machine-readable status."""

    method: str
    path: str
    status: int

    def __str__(self) -> str:
        return f"local environment request {self.method} {self.path} failed with HTTP {self.status}"
