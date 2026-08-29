#!/usr/bin/env python3
"""把 build-profile trust envelope 嵌入一个 iOS 构建产物的资源目录。

生产 Runner 与 Patrol UAT test host 两个 Xcode 工程调用同一份实现：宿主 bundle 里的
trust envelope 与生产 App 受同一组判否约束，否则「宿主起得来」证明不了生产启动路径。
两个工程的 configuration 命名不同（生产带 buildProfile flavor 后缀，宿主没有），因此
build profile 由调用方显式交出，本脚本不从 configuration 名反推。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_APP_DIR = Path(__file__).resolve().parents[2]
_GENERATED_CONTRACT_PATH = (
    _APP_DIR
    / "tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)


def _generated_contract() -> dict[str, object]:
    try:
        contract = json.loads(_GENERATED_CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"generated app launch contract is unavailable: {exc}") from exc
    if (
        not isinstance(contract, dict)
        or contract.get("schema") != "qwq.app-launch-contract.generated"
        or not isinstance(contract.get("sourceDigest"), str)
    ):
        raise SystemExit("generated app launch contract identity is invalid")
    return contract


def _verified_trust_envelope(trust_path: Path, build_profile: str) -> None:
    contract = _generated_contract()
    schemas = contract.get("schemaValues")
    required_fields = contract.get("schemaRequiredFields")
    build_profiles = contract.get("buildProfileEnvironments")
    error_codes = contract.get("runtimeConfigErrorCodes")
    signature_algorithm = contract.get("runtimeConfigPackageSignatureAlgorithm")
    if (
        not isinstance(schemas, dict)
        or not isinstance(required_fields, dict)
        or not isinstance(build_profiles, dict)
        or not isinstance(error_codes, dict)
        or "runtime_config_trust_missing" not in error_codes
    ):
        raise SystemExit("generated app launch trust contract is incomplete")
    trust_fields = required_fields.get("runtime_config_trust_envelope")
    trust_schema = schemas.get("runtime_config_trust_envelope")
    if (
        not isinstance(trust_fields, list)
        or not all(isinstance(field, str) for field in trust_fields)
        or not isinstance(trust_schema, str)
        or build_profile not in build_profiles
        or not isinstance(signature_algorithm, str)
    ):
        raise SystemExit("generated app launch trust contract is invalid")
    if (
        not trust_path.is_absolute()
        or trust_path.is_symlink()
        or not trust_path.is_file()
    ):
        raise SystemExit(
            "runtime trust envelope must be an absolute regular non-symlink file"
        )
    if trust_path.stat().st_size <= 0 or trust_path.stat().st_size > 1024 * 1024:
        raise SystemExit("runtime trust envelope size is invalid")
    try:
        trust = json.loads(trust_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"runtime trust envelope is malformed: {exc}") from exc
    if not isinstance(trust, dict) or set(trust) != set(trust_fields):
        raise SystemExit(
            "runtime trust envelope fields do not match the canonical schema"
        )
    if (
        trust.get("schema") != trust_schema
        or trust.get("buildProfile") != build_profile
        or trust.get("signatureAlgorithm") != signature_algorithm
    ):
        raise SystemExit(
            "runtime trust envelope identity conflicts with Xcode configuration"
        )
    keyring = trust.get("trustedPublicKeys")
    if not isinstance(keyring, dict) or not keyring:
        raise SystemExit("runtime trust envelope keyring is missing")
    for key_id, encoded_key in keyring.items():
        if (
            not isinstance(key_id, str)
            or not key_id
            or len(key_id) > 128
            or not key_id[0].isalnum()
            or any(not (character.isalnum() or character in "._-") for character in key_id)
        ):
            raise SystemExit("runtime trust envelope contains an invalid key id")
        if not isinstance(encoded_key, str):
            raise SystemExit("runtime trust envelope public key must be base64 text")
        try:
            raw_key = base64.b64decode(encoded_key, validate=True)
        except ValueError as exc:
            raise SystemExit(
                "runtime trust envelope public key is not strict base64"
            ) from exc
        if len(raw_key) != 32 or base64.b64encode(raw_key).decode("ascii") != encoded_key:
            raise SystemExit(
                "runtime trust envelope public key is not canonical Ed25519"
            )


def _embed(trust_path: Path, resource_root: Path) -> None:
    resource_root.mkdir(parents=True, exist_ok=True)
    # target runtime package 不得随构建进入产物：装配期只交 trust envelope，package 由
    # 运行时 activation 供给。资源目录可被增量构建复用，因此每次都清掉残留 package。
    package_destination = resource_root / "runtime-config-package.json"
    if package_destination.exists() or package_destination.is_symlink():
        package_destination.unlink()
    destination = resource_root / "runtime-config-trust.json"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(trust_path, temporary)
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        raise SystemExit(
            "usage: build_embed_runtime_config_trust.py "
            "<trust-path> <build-profile> <target-build-dir> <resources-folder-path>"
        )
    trust_path = Path(argv[1]).expanduser()
    build_profile = argv[2].strip()
    if not build_profile:
        raise SystemExit("build profile must be declared by the calling build phase")
    _verified_trust_envelope(trust_path, build_profile)
    _embed(trust_path, Path(argv[3]) / argv[4] / "qwq_runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
