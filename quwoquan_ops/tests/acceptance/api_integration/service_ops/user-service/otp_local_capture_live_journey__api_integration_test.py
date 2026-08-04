"""Live SendOtp → local_capture → protected read → LoginWithPhone journey.

spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-009
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    open_local_phone_acceptance_session,
)
from quwoquan_ops.cli.lib.port_manifest import (  # noqa: E402
    load_port_manifest,
    profile_ports,
)


def _probe(url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def main() -> int:
    environment = "gamma"
    target_name = "gamma-local"
    target = get_target(load_environment_topology(), target_name)
    ports = profile_ports(load_port_manifest(), str(target["portProfile"]))
    api_base = str((target.get("publicBases") or {}).get("api") or "").rstrip("/")
    substitute_health = f"https://127.0.0.1:{ports['sms-provider-substitute']}/healthz"
    user_health = f"http://127.0.0.1:{ports['user-service']}/healthz"
    integration_health = f"http://127.0.0.1:{ports['integration-service']}/healthz"

    missing = [
        name
        for name, url in (
            ("api-edge", api_base + "/healthz" if api_base else ""),
            ("user-service", user_health),
            ("integration-service", integration_health),
            ("sms-provider-substitute", substitute_health),
        )
        if not url or not _probe(url)
    ]
    if missing:
        payload = {
            "schema": "otp-local-capture-live-journey",
            "status": "GATE_BLOCK",
            "reason": "required OTP login runtime is unavailable",
            "missing": missing,
            "target": target_name,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(
            "GATE_BLOCK: live SendOtp→sms-provider-substitute→protected-read→"
            "LoginWithPhone requires healthy "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    actor = open_local_phone_acceptance_session(
        api_base,
        environment=environment,
        target_name=target_name,
        dataset_epoch="a" * 64,
        dataset_id="nonprod_reference_identity",
        actor_role="primary",
        actor_index=0,
    )
    if not actor.session.owner_id or not actor.session.access_token:
        print("GATE_BLOCK: phone acceptance session missing owner/token", file=sys.stderr)
        return 2
    if actor.challenge_id == "":
        print("GATE_BLOCK: OTP challengeId missing from SendOtp response", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": "otp-local-capture-live-journey",
                "status": "passed",
                "target": target_name,
                "challengePresent": True,
                "sessionPresent": True,
                "nonPromotable": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
