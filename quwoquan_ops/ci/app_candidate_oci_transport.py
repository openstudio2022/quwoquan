#!/usr/bin/env python3
"""Move App matrix shards through exact OCI refs without Actions Artifact."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PLATFORMS = ("android", "ios", "web", "macos")
ARCHIVE_NAME = "app-candidate-shard.tar.gz"
ARTIFACT_TYPE = "application/vnd.quwoquan.app-candidate-shard"
LAYER_TYPE = "application/vnd.quwoquan.app-candidate-shard+tar+gzip"
OCI_REF_PATTERN = re.compile(
    r"(?P<repository>ghcr\.io/[a-z0-9._/-]+)@(?P<digest>sha256:[0-9a-f]{64})"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser("publish-shard")
    publish.add_argument("--bundle-dir", required=True, type=Path)
    publish.add_argument("--repository", required=True)
    publish.add_argument("--transport-tag", required=True)

    materialize = subparsers.add_parser("materialize-shards")
    materialize.add_argument("--bundle-dir", required=True, type=Path)
    materialize.add_argument("--repository-prefix", required=True)
    materialize.add_argument("--transport-tag", required=True)
    return parser


def _files(root: Path) -> list[Path]:
    resolved = root.expanduser().resolve()
    if root.is_symlink() or not resolved.is_dir():
        raise ValueError(f"App candidate shard directory is missing or unsafe: {root}")
    entries = sorted(resolved.rglob("*"))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f"App candidate shard contains a symlink: {unsafe}")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f"App candidate shard is empty: {root}")
    return files


def create_archive(bundle_dir: Path, archive_path: Path) -> None:
    """Create one deterministic, path-safe shard layer."""

    root = bundle_dir.expanduser().resolve()
    files = _files(root)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in files:
                    relative = path.relative_to(root).as_posix()
                    info = tarfile.TarInfo(relative)
                    info.size = path.stat().st_size
                    info.mode = 0o644
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with path.open("rb") as source:
                        archive.addfile(info, source)


def _validated_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    if not members:
        raise ValueError("App candidate shard archive is empty")
    for member in members:
        pure = PurePosixPath(member.name)
        if (
            not member.isfile()
            or pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise ValueError(f"App candidate shard archive entry is unsafe: {member.name}")
    return members


def merge_archive(archive_path: Path, bundle_dir: Path) -> None:
    """Extract into isolation and fail on every cross-shard file collision."""

    bundle = bundle_dir.expanduser().resolve()
    bundle.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="app-candidate-shard-extract-") as directory:
        stage = Path(directory)
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = _validated_members(archive)
            for member in members:
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(
                        f"App candidate shard archive file is unreadable: {member.name}"
                    )
                destination = stage.joinpath(*PurePosixPath(member.name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
        for source in sorted(stage.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(stage)
            destination = bundle / relative
            if destination.exists():
                raise ValueError(f"App candidate shard file collision: {relative.as_posix()}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def publish_shard(*, bundle_dir: Path, repository: str, transport_tag: str) -> str:
    if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+", repository) is None:
        raise ValueError("App candidate shard repository is not canonical GHCR")
    if not transport_tag or any(character.isspace() for character in transport_tag):
        raise ValueError("App candidate shard transport tag is invalid")
    with tempfile.TemporaryDirectory(prefix="app-candidate-shard-publish-") as directory:
        root = Path(directory)
        archive_path = root / ARCHIVE_NAME
        create_archive(bundle_dir, archive_path)
        output = _run(
            [
                "oras",
                "push",
                "--no-tty",
                "--artifact-type",
                ARTIFACT_TYPE,
                f"{repository}:{transport_tag}",
                f"{ARCHIVE_NAME}:{LAYER_TYPE}",
                "--format",
                "json",
            ],
            cwd=root,
        )
    payload: Any = json.loads(output)
    exact_ref = str(payload.get("reference") or "") if isinstance(payload, dict) else ""
    match = OCI_REF_PATTERN.fullmatch(exact_ref)
    if match is None or match.group("repository") != repository:
        raise ValueError("ORAS did not return the expected immutable shard reference")
    return exact_ref


def materialize_shards(
    *, bundle_dir: Path, repository_prefix: str, transport_tag: str
) -> dict[str, str]:
    if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+", repository_prefix) is None:
        raise ValueError("App candidate repository prefix is not canonical GHCR")
    bundle = bundle_dir.expanduser().resolve()
    if bundle.exists() and any(bundle.iterdir()):
        raise ValueError("App candidate aggregate destination must start empty")
    bundle.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="app-candidate-shards-pull-") as directory:
        scratch = Path(directory)
        for platform in PLATFORMS:
            for environment in ENVIRONMENTS:
                key = f"{platform}/{environment}"
                repository = (
                    f"{repository_prefix}/app-candidate-shard-{platform}-{environment}"
                )
                tagged_ref = f"{repository}:{transport_tag}"
                exact_ref = _run(["oras", "resolve", "--full-reference", tagged_ref])
                match = OCI_REF_PATTERN.fullmatch(exact_ref)
                if match is None or match.group("repository") != repository:
                    raise ValueError(f"ORAS shard resolution is not immutable: {key}")
                stage = scratch / platform / environment
                stage.mkdir(parents=True)
                _run(["oras", "pull", "--output", str(stage), exact_ref])
                children = list(stage.iterdir())
                if children != [stage / ARCHIVE_NAME]:
                    raise ValueError(f"ORAS shard payload set is not canonical: {key}")
                merge_archive(children[0], bundle)
                refs[key] = exact_ref
    if len(refs) != len(PLATFORMS) * len(ENVIRONMENTS):
        raise ValueError("App candidate matrix shard set is incomplete")
    return refs


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "publish-shard":
            result: Any = {
                "exactRef": publish_shard(
                    bundle_dir=args.bundle_dir,
                    repository=args.repository,
                    transport_tag=args.transport_tag,
                )
            }
        else:
            result = {
                "shards": materialize_shards(
                    bundle_dir=args.bundle_dir,
                    repository_prefix=args.repository_prefix,
                    transport_tag=args.transport_tag,
                )
            }
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        print(f"GATE_BLOCK: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
