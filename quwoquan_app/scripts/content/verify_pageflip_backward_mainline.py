#!/usr/bin/env python3
"""Static gate for the BACK pageflip mainline (forward-isomorphic visual geometry).

This script enforces the architectural rules in
`.cursor/rules/12-pageflip-backward-mainline.mdc`:

1. Forbidden symbols (retired resolvers, host bypass branches, projected-frame
   polygon fields, deprecated soft helpers) must not exist anywhere under the
   generic pageflip engine, article-reader host, or test harness.
2. The retired full-page previous-front baseline
   `ValueKey('article_backward_previous_front_baseline')` must not exist in lib.
3. The portrait BACK invariant must hold:
   - `backward_render_frame_builder.dart` must construct forward-isomorphic
     visual geometry while preserving semantic `direction == back`.
   - `visualGeometryDirection:` and `routeBSpineMirroredApplied:` must remain
     surfaced as diagnostics.
4. `_localPolygonFromArea` MUST contain the StPageFlip BACK drawSoft formula
   `anchor.dx - point.dx`, while forward keeps `point.dx - anchor.dx`.
5. BACK flipping sheet must split recto/front and verso/back inside the same
   soft surface from StPageFlip F/E/clip geometry; diagnostics must expose
   both polygons from the same geometry.
6. `_resolveBackwardDisplayPosition` and the `pageViewportRect` parameter on
   the deprecated soft helper MUST NOT exist anywhere in pageflip code.
7. `ArticlePageBackwardProjectedFrame` must NOT re-introduce polygon fields.

Exits non-zero on any violation. Designed to be cheap and run from
`quwoquan_ops/gate/gate_repo.sh` 的 `run_app`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
APP_TEST = ROOT / "quwoquan_app" / "test"

UI_PAGEFLIP_DIRS = [
    APP_LIB / "components" / "pageflip",
    APP_LIB / "ui" / "content" / "article_reader" / "pageflip",
    # Diagnostics/test harness relocated out of lib/ into test support; forbidden
    # BACK symbols must still be guarded there (R-PAGEFLIP-001/002 收口).
    APP_TEST / "support" / "pageflip",
]

HOST_PATH = (
    APP_LIB
    / "ui"
    / "content"
    / "article_reader"
    / "pageflip"
    / "host"
    / "article_read_only_book_deck.dart"
)
DEBUG_MAPPER_PATH = (
    APP_LIB
    / "ui"
    / "content"
    / "article_reader"
    / "pageflip"
    / "diagnostics"
    / "article_reader_debug_mapper.dart"
)
SOFT_GEOMETRY_PATH = (
    APP_LIB
    / "ui"
    / "content"
    / "article_reader"
    / "pageflip"
    / "layers"
    / "article_reader_soft_page_geometry.dart"
)
PAGEFLIP_WIDGET_TEST_PATH = (
    APP_TEST / "components" / "pageflip" / "pageflip_widget_test.dart"
)
RENDER_FRAME_PATH = APP_LIB / "components" / "pageflip" / "render_frame.dart"
GEOMETRY_PATH = APP_LIB / "components" / "pageflip" / "geometry.dart"
RENDER_FRAME_BUILDER_PATH = (
    APP_LIB / "components" / "pageflip" / "backward_render_frame_builder.dart"
)
OLD_BACKWARD_LEAF_RENDERER_PATH = (
    APP_LIB / "components" / "pageflip" / "backward_leaf_renderer.dart"
)

# Symbols whose mere presence anywhere in pageflip code indicates a regression
# back to the dead M1-A architecture or earlier BACK-branch experiments. They
# were deleted on cutover and must not return.
FORBIDDEN_SYMBOLS = (
    "BackwardFoldSurfaceGeometry",
    "resolveBackwardFoldFrameGeometry",
    "_BackwardDisplaySheetBand",
    "_resolveBackwardDisplaySheetBand",
    "_pageRectBandPolygon",
    "_buildBackwardCurrentResidualLayer",
    "_buildBackwardPreviousLeafSoftLayer",
    "_buildBackwardGeometryProbeSurface",
    "_resolveBackwardFoldSurfaceGeometry",
    "resolveBackwardSheetPartitionFromSheetLocal",
    "_expandDegenerateBackwardVersoPolygon",
    "_resolveBackwardParallelLimitFaceGeometry",
    "_resolveBackwardParallelLimitPairedFaceGeometry",
    "BackwardSheetPartitionSource.parallelLimit",
    "parallelLimitGeometry",
    "_boundLowAngleVersoPolygon",
    "_backwardContinuousFoldEdgeLimitGeometry",
    "BackwardSheetPartitionInput",
    "resolveBackwardSheetPartition(",
    "backwardSheetRectoBudgetFraction",
    "backwardSheetRectoPolygon(",
    "backwardSheetVersoPolygon(",
    "polygonLooksLikeFullPageFallback(",
    "keepPositiveSideForBackwardRecto(",
    # Route B (M1) cutover: BACK soft helper / display-position resolver are
    # all retired. Frame builder X-mirrors area/anchor/angle and BACK reuses
    # forward path; no separate BACK soft geometry helper may exist.
    "_resolveBackwardDisplayPosition",
    "resolveBackwardSoftPageGeometry",
    "_backwardVersoAreaPolygon",
)

# Forbidden polygon fields on ArticlePageBackwardProjectedFrame.
FORBIDDEN_PROJECTED_FRAME_FIELDS = (
    "previousFoldSurfacePolygon",
    "previousBackFoldPolygon",
    "previousFrontFoldPolygon",
    "currentResidualPolygon",
)

BASELINE_VALUE_KEY = "'article_backward_previous_front_baseline'"

# Required strings inside backward_render_frame_builder.dart. Portrait BACK must
# preserve BACK semantics while using forward-isomorphic visual geometry.
REQUIRED_FRAME_BUILDER_STRINGS = (
    "_resolveBackwardVisualGeometry(",
    "resolveBackwardForwardCanonicalPoint(",
    "direction: StPageFlipDirection.forward",
    "visualGeometryDirection: visualGeometry.direction",
    "foldLineSource: 'backwardForwardIsomorphicFoldLine'",
    "edgeLineSource: 'backwardForwardIsomorphicFreeEdgeLine'",
    "routeBSpineMirroredApplied:",
)

FORBIDDEN_FRAME_BUILDER_STRINGS = (
    "_runForwardEquivalentCalc(",
    "_ForwardEquivalentGeometry",
    "_mirrorAreaX(",
    "_mirrorX(",
    "backwardForwardIsomorphicCalcFailed",
    "flippingClipArea: const <ui.Offset>[]",
    "bottomClipArea: const <ui.Offset>[]",
)


def _iter_dart_files() -> list[Path]:
    out: list[Path] = []
    for d in UI_PAGEFLIP_DIRS:
        if not d.exists():
            continue
        out.extend(p for p in d.rglob("*.dart") if p.is_file())
    return sorted(out)


_LINE_COMMENT_RX = re.compile(r"^\s*//")
_BLOCK_COMMENT_RX = re.compile(r"/\*[\s\S]*?\*/")
_PART_DIRECTIVE_RX = re.compile(
    r"^\s*part\s+['\"](?P<uri>[^'\"]+)['\"]\s*;",
    re.MULTILINE,
)


def _strip_comments(src: str) -> str:
    """Remove `//` line comments and `/* */` block comments before scanning.

    Doc comments (`///`) are explanatory prose; they may legitimately mention
    forbidden symbol names while documenting why those symbols were removed.
    The architectural rule applies to executable code only.
    """

    no_block = _BLOCK_COMMENT_RX.sub("", src)
    out_lines: list[str] = []
    for line in no_block.splitlines():
        if _LINE_COMMENT_RX.match(line):
            out_lines.append("")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _host_library_paths() -> tuple[list[Path], list[str]]:
    """解析 host 根文件以及它实际声明的 part 文件。"""

    if not HOST_PATH.exists():
        return [], [f"missing host: {HOST_PATH.relative_to(ROOT)}"]
    root_source = HOST_PATH.read_text(encoding="utf-8")
    host_dir = HOST_PATH.parent.resolve()
    declared_paths: list[Path] = []
    violations: list[str] = []
    seen: set[Path] = set()
    for match in _PART_DIRECTIVE_RX.finditer(root_source):
        uri = match.group("uri")
        candidate = (HOST_PATH.parent / uri).resolve()
        if candidate.parent != host_dir:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: part `{uri}` must stay in the host directory"
            )
            continue
        if candidate in seen:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: duplicate part declaration `{uri}`"
            )
            continue
        seen.add(candidate)
        if not candidate.is_file():
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: declared part `{uri}` is missing"
            )
            continue
        declared_paths.append(candidate)

    deck_parts = set(
        HOST_PATH.parent.glob(f"{HOST_PATH.stem}_*.dart"),
    )
    for orphan in sorted(deck_parts - seen):
        violations.append(
            f"{orphan.relative_to(ROOT)}: deck part exists but is not declared by "
            f"{HOST_PATH.relative_to(ROOT)}"
        )
    return [HOST_PATH, *declared_paths], violations


def _host_library_text() -> str:
    paths, _ = _host_library_paths()
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _check_host_library_parts() -> list[str]:
    _, violations = _host_library_paths()
    return violations


def _read_scan_source(path: Path) -> str:
    if path == HOST_PATH:
        return _host_library_text()
    return path.read_text(encoding="utf-8")


def _check_forbidden_symbols() -> list[str]:
    violations: list[str] = []
    for path in _iter_dart_files():
        text = _strip_comments(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for sym in FORBIDDEN_SYMBOLS:
            if sym in text:
                violations.append(
                    f"{rel}: forbidden symbol `{sym}` (Route-B mainline disallows the retired bypass; see .cursor/rules/12-pageflip-backward-mainline.mdc)"
                )
    return violations


def _check_no_previous_front_baseline() -> list[str]:
    violations: list[str] = []
    for path in _iter_dart_files():
        text = path.read_text(encoding="utf-8")
        if BASELINE_VALUE_KEY in text:
            violations.append(
                f"{path.relative_to(ROOT).as_posix()}: forbidden full previous-front "
                f"baseline ValueKey {BASELINE_VALUE_KEY}; BACK previous front must only "
                "be painted by the recto slice inside the moving sheet."
            )
    return violations


def _check_no_retired_backward_leaf_renderer() -> list[str]:
    if OLD_BACKWARD_LEAF_RENDERER_PATH.exists():
        return [
            f"{OLD_BACKWARD_LEAF_RENDERER_PATH.relative_to(ROOT)}: retired "
            "`ArticlePageBackwardLeafRenderer` path must stay deleted; BACK "
            "mainline must use the single forward-isomorphic vertices/UV path."
        ]
    return []


def _check_frame_builder_native_back() -> list[str]:
    """Frame builder must preserve BACK semantics and use forward-isomorphic visual geometry."""

    violations: list[str] = []
    if not RENDER_FRAME_BUILDER_PATH.exists():
        violations.append(
            f"missing builder: {RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}"
        )
        return violations
    builder = RENDER_FRAME_BUILDER_PATH.read_text(encoding="utf-8")
    for required in REQUIRED_FRAME_BUILDER_STRINGS:
        if required not in builder:
            violations.append(
                f"{RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}: missing required Route-B (M1) marker `{required}`. "
                "BACK frame builder must preserve semantic BACK while using forward-isomorphic visual geometry."
            )
    for forbidden in FORBIDDEN_FRAME_BUILDER_STRINGS:
        if forbidden in builder:
            violations.append(
                f"{RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}: forbidden native-BACK regression marker `{forbidden}`. "
                "Do not restore retired mirror helpers or bypass geometry."
            )
    return violations


def _extract_method_body(text: str, signature_pattern: str) -> str | None:
    m = re.search(signature_pattern, text, re.DOTALL)
    if m is None:
        return None
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _check_native_back_draw_soft_in_host_helpers() -> list[str]:
    """`_localPolygonFromArea` must implement StPageFlip BACK drawSoft.

    BACK is allowed only as the native local clip formula in `_localPolygonFromArea`.
    Do not re-introduce old helper layers or display-position resolvers.
    """

    violations: list[str] = []
    if not HOST_PATH.exists():
        violations.append(f"missing host: {HOST_PATH.relative_to(ROOT)}")
        return violations
    text = _strip_comments(_host_library_text())

    soft_body = _extract_method_body(
        text,
        r"Widget _buildSoftPageLayer\([^)]*\)\s*\{",
    )
    if soft_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse `_buildSoftPageLayer` body"
        )
    else:
        if "resolveBackwardSoftPageGeometry(" in soft_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_buildSoftPageLayer` must not call "
                "deprecated `resolveBackwardSoftPageGeometry`."
            )
        for marker in (
            "final useBackwardMaterialSheet",
            "sheetMaterialLocalPolygon",
            "pageRectPolygon(pageSize)",
        ):
            if marker not in soft_body:
                violations.append(
                    f"{HOST_PATH.relative_to(ROOT)}: `_buildSoftPageLayer` missing "
                    f"material-locked BACK UV marker `{marker}`. BACK verso texture "
                    "must use full material-local sheet coordinates while "
                    "geometry keeps using `flippingClipArea` only as a clip."
                )
        for forbidden in (
            "_backwardVersoAreaPolygon(",
            "materialLocalPolygon: polygon",
        ):
            if forbidden in soft_body:
                violations.append(
                    f"{HOST_PATH.relative_to(ROOT)}: `_buildSoftPageLayer` must not use "
                    f"`{forbidden}`; BACK UV cannot be derived from the dynamic visible clip."
                )
        if "sheetAreaPolygon: area," in soft_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_buildSoftPageLayer` must not pass "
                "`sheetAreaPolygon: area` for BACK; `area` is the moving visible "
                "flippingClipArea window and reintroduces texture scanning."
            )

    poly_body = _extract_method_body(
        text,
        r"Offset\s+_localPointFromAreaPoint\([^)]*\)\s*\{",
    )
    if poly_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse `_localPointFromAreaPoint` body"
        )
    else:
        if "direction == StPageFlipDirection.back" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPointFromAreaPoint` must contain the "
                "native StPageFlip BACK branch."
            )
        if "anchor.dx - point.dx" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPointFromAreaPoint` must implement "
                "`anchor.dx - point.dx` for BACK drawSoft."
            )
        if "point.dx - anchor.dx" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPointFromAreaPoint` must keep "
                "`point.dx - anchor.dx` for FORWARD drawSoft."
            )

    return violations


def _check_recto_verso_split_in_host() -> list[str]:
    """Enforce Route-B: L0 current underlay + one split moving leaf."""
    violations: list[str] = []
    host = _strip_comments(_host_library_text())
    dynamic_path = HOST_PATH.parent / "article_read_only_book_deck_dynamic_layers.dart"
    soft_path = HOST_PATH.parent / "article_read_only_book_deck_soft_layers.dart"
    diagnostic_path = (
        HOST_PATH.parent / "article_read_only_book_deck_diagnostic_geometry.dart"
    )
    dynamic = _strip_comments(dynamic_path.read_text(encoding="utf-8")) if dynamic_path.exists() else ""
    soft = _strip_comments(soft_path.read_text(encoding="utf-8")) if soft_path.exists() else ""
    diagnostic = (
        _strip_comments(diagnostic_path.read_text(encoding="utf-8"))
        if diagnostic_path.exists()
        else ""
    )

    for retired in (
        "_buildBackwardPageSpaceReplacementLayer",
        "_buildBackwardFullSheetBackSurface",
        "article_backward_previous_front_baseline",
    ):
        if retired in host:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: Route-B must not restore retired BACK replacement {retired!r}."
            )

    backward_layers = _extract_method_body(
        dynamic,
        r"ArticleReadOnlyBookRenderBranch\s+_buildBackwardDynamicLayers\([^)]*\)\s*\{",
    )
    if backward_layers is None:
        violations.append(
            f"{dynamic_path.relative_to(ROOT)}: missing _buildBackwardDynamicLayers."
        )
    else:
        bottom_index = backward_layers.find("scene.bottomPageIndex")
        flipping_index = backward_layers.find("frame.flippingClipArea")
        if bottom_index < 0 or flipping_index < 0 or bottom_index > flipping_index:
            violations.append(
                f"{dynamic_path.relative_to(ROOT)}: Route-B must paint current L0 underlay before the flipping L1 sheet."
            )
        for marker in (
            "pageIndex: scene.bottomPageIndex!",
            "pageIndex: flippingPageIndex",
            "backFacePageIndex: textureBinding?.versoPageIndex",
            "backwardLeafFrame: frame.backwardLeafFrame",
        ):
            if marker not in backward_layers:
                violations.append(
                    f"{dynamic_path.relative_to(ROOT)}: Route-B is missing binding marker {marker!r}."
                )

    split_body = _extract_method_body(
        soft,
        r"Widget\s+_buildBackwardSplitFlippingSurface\([^)]*\)\s*\{",
    )
    if split_body is None:
        violations.append(
            f"{soft_path.relative_to(ROOT)}: missing single moving-sheet recto/verso surface."
        )
    else:
        for marker in (
            "coveredWidthNormalized",
            "totalRectoVisibleWidthNormalized",
            "resolveArticlePageBackwardSheetLocalSlices",
            "_buildBackwardSheetFaceSlice(",
            "ArticlePageSurfaceKind.front",
            "ArticlePageSurfaceKind.back",
            "article_backward_flipping_recto_slice",
            "article_backward_flipping_verso_slice",
        ):
            if marker not in split_body:
                violations.append(
                    f"{soft_path.relative_to(ROOT)}: moving-sheet split is missing {marker!r}."
                )
        if "progress >" in split_body or "progress <" in split_body:
            violations.append(
                f"{soft_path.relative_to(ROOT)}: BACK must not choose a face from progress."
            )
        for marker in (
            "resolveBackwardCanonicalSheetFaces",
            "BackwardCanonicalSheetInput",
        ):
            if marker in split_body or marker in diagnostic:
                violations.append(
                    f"{soft_path.relative_to(ROOT)}: BACK recto/verso must consume "
                    "ArticlePageBackwardLeafFrame sheet-local intervals, not "
                    f"{marker!r}."
                )
        if "resolveArticlePageBackwardSheetLocalSlices" not in diagnostic:
            violations.append(
                f"{diagnostic_path.relative_to(ROOT)}: diagnostics must consume "
                "the same leaf-frame sheet-local slice resolver as paint."
            )

    soft_layer_body = _extract_method_body(
        soft, r"Widget\s+_buildSoftPageLayer\([^)]*\)\s*\{"
    )
    if soft_layer_body is None:
        violations.append(
            f"{soft_path.relative_to(ROOT)}: missing shared _buildSoftPageLayer."
        )
    else:
        for marker in (
            "Transform.rotate(",
            "ClipPath(",
            "Transform.translate(",
            "offset: -paintOrigin",
            "_buildSoftFlippingPageSurface(",
        ):
            if marker not in soft_layer_body:
                violations.append(
                    f"{soft_path.relative_to(ROOT)}: BACK faces must share outer soft sheet {marker!r}."
                )

    return violations


def _check_backward_texture_binding() -> list[str]:
    violations: list[str] = []
    snapshot_path = APP_LIB / "components" / "pageflip" / "page_surface_snapshot.dart"
    if not snapshot_path.exists():
        violations.append(f"missing snapshot binding: {snapshot_path.relative_to(ROOT)}")
        return violations
    text = _strip_comments(snapshot_path.read_text(encoding="utf-8"))
    if "int get leafVersoPageIndex => leafPageIndex" not in text:
        violations.append(
            f"{snapshot_path.relative_to(ROOT)}: BACK leaf verso must resolve to leafPageIndex, "
            "not covered/current page."
        )
    binding_body = _extract_method_body(
        text,
        r"ArticlePageTextureBinding\?\s+resolveArticlePageTextureBinding\([^)]*\)\s*\{",
    )
    if binding_body is None:
        violations.append(
            f"{snapshot_path.relative_to(ROOT)}: failed to parse resolveArticlePageTextureBinding body"
        )
    else:
        back_return_index = binding_body.rfind("return ArticlePageTextureBinding(")
        back_body = binding_body[back_return_index:] if back_return_index >= 0 else binding_body
        if "versoPageIndex: flippingPageIndex" not in back_body:
            violations.append(
                f"{snapshot_path.relative_to(ROOT)}: BACK texture binding must use "
                "`versoPageIndex: flippingPageIndex` for the previous leaf backside."
            )
        if "versoPageIndex: currentPageIndex" in back_body:
            violations.append(
                f"{snapshot_path.relative_to(ROOT)}: BACK texture binding must not use "
                "`versoPageIndex: currentPageIndex`."
            )
        if "bottomPageIndex: currentPageIndex" not in back_body:
            violations.append(
                f"{snapshot_path.relative_to(ROOT)}: BACK texture binding must keep current "
                "only as `bottomPageIndex: currentPageIndex`."
            )
    return violations


def _check_soft_geometry_helper_clean() -> list[str]:
    """`article_reader_soft_page_geometry.dart` must not expose BACK-specific helpers.

    `_resolveBackwardDisplayPosition`, `pageViewportRect` parameter, and
    `resolveBackwardSoftPageGeometry` stay retired. `softLayerViewportDirection`
    must return the active direction, matching StPageFlip `convertToGlobal`.
    """

    violations: list[str] = []
    if not SOFT_GEOMETRY_PATH.exists():
        violations.append(
            f"missing soft geometry: {SOFT_GEOMETRY_PATH.relative_to(ROOT)}"
        )
        return violations
    text = SOFT_GEOMETRY_PATH.read_text(encoding="utf-8")
    text_no_comments = _strip_comments(text)
    forbidden = (
        "_resolveBackwardDisplayPosition",
        "resolveBackwardSoftPageGeometry",
    )
    for sym in forbidden:
        if sym in text_no_comments:
            violations.append(
                f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: forbidden BACK soft helper `{sym}` "
                "still present (Route-B retired all BACK soft helpers; mirror lives in frame builder)."
            )
    # The pageViewportRect parameter only existed on the retired backward soft
    # geometry resolver. Forbid both the parameter declaration and any
    # call-site that still threads it into a soft helper.
    if re.search(r"\bpageViewportRect\b\s*:", text_no_comments):
        violations.append(
            f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: `pageViewportRect` parameter must be removed "
            "(belonged to deprecated BACK soft helper)."
        )

    # softLayerViewportDirection must return the active direction.
    m = re.search(
        r"StPageFlipDirection\s+softLayerViewportDirection\([^)]*\)\s*\{([\s\S]*?)\}\s*\n",
        text_no_comments,
    )
    if m is None:
        violations.append(
            f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: missing softLayerViewportDirection definition"
        )
    else:
        body = m.group(1)
        if "return direction" not in body:
            violations.append(
                f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: softLayerViewportDirection must always "
                "return the active geometry direction."
            )
    return violations


def _check_projected_frame_fields() -> list[str]:
    violations: list[str] = []
    if not RENDER_FRAME_PATH.exists():
        violations.append(f"missing render frame: {RENDER_FRAME_PATH.relative_to(ROOT)}")
        return violations
    rf = _strip_comments(RENDER_FRAME_PATH.read_text(encoding="utf-8"))
    if "lerpDouble(rectoCoverageByFold, 1.0" in rf:
        violations.append(
            f"{RENDER_FRAME_PATH.relative_to(ROOT)}: BACK rectoCoverage must not "
            "settle-interpolate to 1.0 while still in paperFoldDynamic; that "
            "reintroduces front-dominant contamination."
        )
    # Look only inside the ArticlePageBackwardProjectedFrame class.
    m = re.search(
        r"class\s+ArticlePageBackwardProjectedFrame\b[\s\S]*?\}\s*\n",
        rf,
    )
    block = m.group(0) if m else rf
    for field in FORBIDDEN_PROJECTED_FRAME_FIELDS:
        if field in block:
            violations.append(
                f"{RENDER_FRAME_PATH.relative_to(ROOT)}: ArticlePageBackwardProjectedFrame must not declare polygon field `{field}`"
            )
    if not RENDER_FRAME_BUILDER_PATH.exists():
        violations.append(
            f"missing builder: {RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}"
        )
        return violations
    builder = _strip_comments(RENDER_FRAME_BUILDER_PATH.read_text(encoding="utf-8"))
    for field in FORBIDDEN_PROJECTED_FRAME_FIELDS:
        if field in builder:
            violations.append(
                f"{RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}: must not produce polygon field `{field}`"
            )
    return violations


def _check_backward_visual_replay_mapping() -> list[str]:
    violations: list[str] = []
    if not GEOMETRY_PATH.exists():
        violations.append(f"missing geometry: {GEOMETRY_PATH.relative_to(ROOT)}")
        return violations
    geometry = _strip_comments(GEOMETRY_PATH.read_text(encoding="utf-8"))
    body = _extract_method_body(
        geometry,
        r"Offset\s+resolveBackwardVisualReplayCanonicalPoint\([^)]*\)\s*\{",
    )
    if body is None:
        violations.append(
            f"{GEOMETRY_PATH.relative_to(ROOT)}: missing resolveBackwardVisualReplayCanonicalPoint"
        )
        return violations
    required_markers = (
        "-pageWidth",
        "pageWidth - edgeEpsilon",
        "dragProgress",
        "visualProgress",
        "2 * pageWidth * visualProgress",
    )
    for marker in required_markers:
        if marker not in body:
            violations.append(
                f"{GEOMETRY_PATH.relative_to(ROOT)}: BACK visual replay mapping must keep marker `{marker}` "
                "so portrait BACK starts from the forward completed negative-X pose."
            )
    if "clamp(0.0, pageWidth)" in body:
        violations.append(
            f"{GEOMETRY_PATH.relative_to(ROOT)}: BACK visual replay mapping must not clamp visual X to 0..pageWidth."
        )
    return violations


def main() -> int:
    if not APP_LIB.exists():
        print(f"pageflip_backward_mainline: FAIL missing {APP_LIB}", file=sys.stderr)
        return 1

    violations: list[str] = []
    violations.extend(_check_forbidden_symbols())
    violations.extend(_check_no_previous_front_baseline())
    violations.extend(_check_no_retired_backward_leaf_renderer())
    violations.extend(_check_host_library_parts())
    violations.extend(_check_frame_builder_native_back())
    violations.extend(_check_native_back_draw_soft_in_host_helpers())
    violations.extend(_check_recto_verso_split_in_host())
    violations.extend(_check_backward_texture_binding())
    violations.extend(_check_soft_geometry_helper_clean())
    violations.extend(_check_projected_frame_fields())
    violations.extend(_check_backward_visual_replay_mapping())

    if violations:
        print("pageflip_backward_mainline: FAIL", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "  see: .cursor/rules/12-pageflip-backward-mainline.mdc",
            file=sys.stderr,
        )
        return 1

    print("pageflip_backward_mainline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
