"""Canonical source identities for the two independent iOS Pod hosts."""

from __future__ import annotations

from pathlib import Path

from .dependency_fs import assert_real_directory

IOS_POD_PRODUCTION_HOST = "production"
IOS_POD_PATROL_HOST = "patrol"
IOS_POD_HOSTS = (IOS_POD_PRODUCTION_HOST, IOS_POD_PATROL_HOST)
IOS_NATIVE_DEPENDENCY_MODE = "cocoapods"
IOS_FLUTTER_SWIFT_PACKAGE_MANAGER = "false"

IOS_POD_DEPENDENCY_LOGICAL_PATHS = {
    IOS_POD_PRODUCTION_HOST: "dependency:production-ios-cocoapods-v2",
    IOS_POD_PATROL_HOST: "dependency:patrol-host-ios-cocoapods-v2",
}
IOS_POD_DEPENDENCY_DIRECTORIES = {
    IOS_POD_PRODUCTION_HOST: Path("dependencies/production-ios-cocoapods"),
    IOS_POD_PATROL_HOST: Path("dependencies/patrol-host-ios-cocoapods"),
}
IOS_PODFILE_RELATIVES = {
    IOS_POD_PRODUCTION_HOST: Path("quwoquan_app/ios/Podfile"),
    IOS_POD_PATROL_HOST: Path("quwoquan_app/test_host/patrol/ios/Podfile"),
}

_EXCLUDED_SEGMENTS = frozenset(
    {".dart_tool", ".symlinks", "Flutter", "Pods", "build", "example", "macos"}
)


def validate_ios_pod_host(value: str) -> str:
    host = str(value or "")
    if host not in IOS_POD_HOSTS:
        raise ValueError("iOS Pod dependency host is unsupported")
    return host


def ios_pod_resolution_inputs(
    *, repo_root: Path, dependency_host: str
) -> dict[str, Path]:
    """Return the host Podfile and every repo-local iOS plugin podspec.

    Hosted plugin podspecs are already transitively bound by the host's Pub
    cache digest.  This set therefore contains only authoring bytes from the
    repository, never generated ``.symlinks`` or ``Flutter.podspec`` files.
    """

    host = validate_ios_pod_host(dependency_host)
    root = repo_root.expanduser().absolute()
    assert_real_directory(root, label="iOS Pod resolution repository root")
    if host == IOS_POD_PRODUCTION_HOST:
        from .pub_cache_store import pub_resolution_input_paths

        pubspecs = pub_resolution_input_paths(root)
    else:
        from .patrol_pub_cache import patrol_resolution_input_paths

        pubspecs = patrol_resolution_input_paths(root)
    app_root = root / "quwoquan_app"
    paths: set[Path] = {root / IOS_PODFILE_RELATIVES[host]}
    for pubspec in pubspecs:
        if pubspec.name != "pubspec.yaml" or pubspec.parent == app_root:
            continue
        for native_name in ("ios", "darwin"):
            native_root = pubspec.parent / native_name
            if not native_root.is_dir() or native_root.is_symlink():
                continue
            for candidate in native_root.rglob("*"):
                relative = candidate.relative_to(root)
                if any(segment in _EXCLUDED_SEGMENTS for segment in relative.parts):
                    continue
                if candidate.name.endswith((".podspec", ".podspec.json")):
                    paths.add(candidate)
    if host == IOS_POD_PRODUCTION_HOST:
        commercial = app_root / "vendor/commercial_auth"
        if commercial.is_dir() and not commercial.is_symlink():
            for candidate in commercial.glob("*/ios/*.podspec"):
                paths.add(candidate)
    result = {
        path.relative_to(root).as_posix(): path
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
    }
    expected_podfile = IOS_PODFILE_RELATIVES[host].as_posix()
    if expected_podfile not in result or not any(
        logical.endswith((".podspec", ".podspec.json")) for logical in result
    ):
        raise ValueError("iOS Pod resolution input closure is incomplete")
    return result
