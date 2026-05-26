#!/usr/bin/env python3
"""Static gate for the BACK pageflip mainline (forward-isomorphic visual geometry).

This script enforces the architectural rules in
`.cursor/rules/12-pageflip-backward-mainline.mdc`:

1. Forbidden symbols (retired resolvers, host bypass branches, projected-frame
   polygon fields, deprecated soft helpers) must not exist anywhere under
   `quwoquan_app/lib/ui/content/...`.
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
`scripts/gate_repo.sh` `run_app`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
APP_TEST = ROOT / "quwoquan_app" / "test"

UI_PAGEFLIP_DIRS = [
    APP_LIB / "ui" / "content" / "pageflip",
    APP_LIB / "ui" / "content" / "article_reader" / "pageflip",
    APP_LIB / "components" / "pageflip",
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
PARTITION_PATH = (
    APP_LIB
    / "ui"
    / "content"
    / "article_reader"
    / "pageflip"
    / "layers"
    / "backward_sheet_partition.dart"
)
PAGEFLIP_WIDGET_TEST_PATH = (
    APP_TEST / "components" / "pageflip" / "pageflip_widget_test.dart"
)
RENDER_FRAME_PATH = APP_LIB / "ui" / "content" / "pageflip" / "render_frame.dart"
GEOMETRY_PATH = APP_LIB / "ui" / "content" / "pageflip" / "geometry.dart"
RENDER_FRAME_BUILDER_PATH = (
    APP_LIB / "ui" / "content" / "pageflip" / "backward_render_frame_builder.dart"
)
OLD_BACKWARD_LEAF_RENDERER_PATH = (
    APP_LIB / "ui" / "content" / "pageflip" / "backward_leaf_renderer.dart"
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
    "resolveBackwardVisualReplayLocalPagePoint(",
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
            "mainline must use the single forward-compatible vertices/UV path."
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
    text = _strip_comments(HOST_PATH.read_text(encoding="utf-8"))

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
    violations: list[str] = []
    if not HOST_PATH.exists():
        violations.append(f"missing host: {HOST_PATH.relative_to(ROOT)}")
        return violations
    text = _strip_comments(HOST_PATH.read_text(encoding="utf-8"))
    required_markers = (
        "_buildBackwardCanonicalFlippingPageSurface(",
        "_buildBackwardSheetFacePolygon(",
        "_buildBackwardBackFoldBandSurface(",
        "resolveBackwardCanonicalSheetFaces(",
        "BackwardCanonicalSheetInput(",
        "backwardFreeEdgeLine:",
        "projectedRightEdgeLine",
        "backwardLeafFrame: frame.backwardLeafFrame",
        "backwardFoldLine: frame.backwardProjectedFrame?.foldLine",
        "ArticlePageSurfaceKind.front",
        "ArticlePageSurfaceKind.back",
        "_buildBackwardVersoTextureSurface(",
        "clipBehavior: Clip.none",
        "previousBackLocalPolygon",
        "transformSoftLayerLocalPolygon(",
    )
    for marker in required_markers:
        if marker not in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: missing recto/verso BACK split marker `{marker}`. "
                "BACK Route-B must compose frontFlat(S-E), backBand(E-F), and currentResidual(F-R)."
            )

    if "_singlePageBackwardFlippingDisplayOffset" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK render/diagnostics must not use "
            "`_singlePageBackwardFlippingDisplayOffset`; use the single native "
            "BACK drawSoft projection."
        )
    if "_reflectionMatrixForLine" in text or "_buildBackwardRectoFacePolygon" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front must not use the "
            "regressed reflection Transform path; split the existing sheet by F/E geometry."
        )
    if "_buildBackwardLaidDownFrontLayer" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK previous-front must not use the old standalone "
            "full pageRect layer; derive the Route-B flat segment from E/free-edge."
        )
    if "backFacePageIndex: scene.currentPageIndex" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back fold band must not bind "
            "to the covered current page; verso belongs to the flipping previous leaf."
        )
    if "controller.applyAnimationFrame(plan.frames[lastFrameIndex])" not in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: page flip completion must apply the final "
            "animation frame before committing the static page."
        )

    diag_body = _extract_method_body(
        text,
        r"_BackwardDiagnosticGeometry\?\s+_resolveBackwardDiagnosticGeometry\([^)]*\)\s*\{",
    )
    if diag_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse `_resolveBackwardDiagnosticGeometry` body"
        )
    else:
        if "previousFrontViewportBounds: null" in diag_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_resolveBackwardDiagnosticGeometry` must no longer "
                "force previousFrontViewportBounds to null."
            )
        if "previousFrontLocalPolygon: const <Offset>[]" in diag_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_resolveBackwardDiagnosticGeometry` must derive "
                "previousFrontLocalPolygon from the recto split, not hard-code an empty polygon."
            )
        if "resolveBackwardCanonicalSheetFaces(" not in diag_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_resolveBackwardDiagnosticGeometry` must consume "
                "the shared canonical BACK face resolver used by rendering."
            )

    if not SOFT_GEOMETRY_PATH.exists():
        violations.append(f"missing soft geometry: {SOFT_GEOMETRY_PATH.relative_to(ROOT)}")
    else:
        soft_geometry_text = _strip_comments(
            SOFT_GEOMETRY_PATH.read_text(encoding="utf-8")
        )
        if "narrowBackwardBackBandPolygon(" in soft_geometry_text:
            violations.append(
                f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: BACK back band must not be "
                "narrowed with synthetic vertical guard lines; consume StPageFlip F/E geometry."
            )
        for forbidden_marker in (
            "keepPositiveSideForBackwardRecto(",
            "backwardSheetRectoPolygon(",
            "backwardSheetVersoPolygon(",
            "polygonLooksLikeFullPageFallback(",
            "backwardSheetRectoBudgetFraction(",
            "rectoRevealWidthNormalized * 0.55",
            "edgeBandWidthNormalized * 0.35",
        ):
            if forbidden_marker in soft_geometry_text:
                violations.append(
                    f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: old BACK ownership/budget "
                    f"marker `{forbidden_marker}` must stay removed; canonical face "
                    "resolver owns BACK geometry."
                )
        for forbidden_marker in (
            "if (leafFrameGeometry != null) {\n    return leafFrameGeometry;",
            "fourLineGeometry.recto.isEmpty",
            "leafFrameGeometry.recto.isNotEmpty",
            "_resolveBackwardLeafFrameFaceGeometry(",
            "return leafFrameGeometry;",
        ):
            if forbidden_marker in soft_geometry_text:
                violations.append(
                    f"{SOFT_GEOMETRY_PATH.relative_to(ROOT)}: BACK low-angle "
                f"ownership must not keep leaf-frame takeover marker `{forbidden_marker}`."
                )
    surface_body = _extract_method_body(
        text,
        r"Widget\s+_buildBackwardCanonicalFlippingPageSurface\([^)]*\)\s*\{",
    )
    if surface_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse "
            "`_buildBackwardCanonicalFlippingPageSurface` body"
        )
    else:
        if "_buildBackwardBackFoldBandSurface(" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back must render as a clipped "
                "fold band with dedicated backside texture/overlay semantics."
            )
        if "_buildBackwardSheetFacePolygon(" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front visible plane must "
                "render through the previous front surface path."
            )
        if "ArticlePageSurfaceKind.front" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front visible plane must "
                "draw the previous front page surface; do not route it to semantic back."
            )
        if "BackwardCanonicalSheetInput(" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK front/back sheet faces must build "
                "the single sheet-local `BackwardCanonicalSheetInput`."
            )
        if "materialLocalPolygon: partition.previousBackVersoAreaPolygon" in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must not pass "
                "`partition.previousBackVersoAreaPolygon` as the main UV source; "
                "that dynamic F/E source area reintroduces visible texture scanning."
            )
        if "materialLocalPolygon: sheetMaterialLocalPolygon" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must pass the "
                "fixed `sheetMaterialLocalPolygon` material domain and use the "
                "partition polygon only as display clip."
            )
        recto_surface_body = surface_body.split(
            "_buildBackwardBackFoldBandSurface("
        )[0]
        if "_buildBackwardVersoTextureSurface(" in recto_surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front visible plane must not "
                "call the verso/back texture painter."
            )
        if "resolveBackwardCanonicalSheetFaces(" not in surface_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK front/back sheet faces must come "
                "from the shared canonical face resolver."
            )

    if "backwardSheetRectoPolygon(" in text or "backwardSheetVersoPolygon(" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK recto/verso polygons must be consumed "
            "through shared canonical face resolver; do not reintroduce duplicate "
            "F/E geometry branches in render or diagnostics."
        )
    recto_face_body = _extract_method_body(
        text,
        r"Widget\s+_buildBackwardSheetFacePolygon\([^)]*\)\s*\{",
    )
    if recto_face_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse "
            "`_buildBackwardSheetFacePolygon` body"
        )
    else:
        if "_buildBackwardSheetPolygonSurface(" not in recto_face_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front must render "
                "through `_buildBackwardSheetPolygonSurface` so sheet-local "
                "polygons with out-of-page bounds do not leak current underlay."
            )
        if "Positioned.fill(" in recto_face_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK recto/front must not use "
                "`Positioned.fill`; it clips sheet-local recto polygons against "
                "the page box and lets current/front leak through."
            )
    if DEBUG_MAPPER_PATH.exists():
        debug_mapper = _strip_comments(DEBUG_MAPPER_PATH.read_text(encoding="utf-8"))
        if "resolveBackwardCanonicalSheetFaces(" not in debug_mapper:
            violations.append(
                f"{DEBUG_MAPPER_PATH.relative_to(ROOT)}: diagnostics must use "
                "the single shared canonical BACK face resolver."
            )
        if "BackwardCanonicalSheetInput(" not in debug_mapper:
            violations.append(
                f"{DEBUG_MAPPER_PATH.relative_to(ROOT)}: diagnostics must construct "
                "the same sheet-local `BackwardCanonicalSheetInput` as host paint."
            )
        if "backwardSheetVersoPolygon(" in debug_mapper:
            violations.append(
                f"{DEBUG_MAPPER_PATH.relative_to(ROOT)}: diagnostics must not "
                "re-derive BACK verso geometry; use shared canonical face resolver."
            )
        if "backwardFrontFlatPolygon(" in debug_mapper:
            violations.append(
                f"{DEBUG_MAPPER_PATH.relative_to(ROOT)}: diagnostics must not restore "
                "the free previous-front flat geometry branch."
            )

    if PARTITION_PATH.exists():
        partition_text = _strip_comments(PARTITION_PATH.read_text(encoding="utf-8"))
        if "class BackwardCanonicalSheetInput" not in partition_text:
            violations.append(
                f"{PARTITION_PATH.relative_to(ROOT)}: missing "
                "`BackwardCanonicalSheetInput`; BACK canonical resolver must have one "
                "explicit sheet-local input contract."
            )
        for marker in (
            "required this.sheetAreaPolygon",
            "previousBackVersoAreaPolygon",
            "previousFrontRectoAreaPolygon",
            "_clipPairedPolygonByLine(",
            "_resolveCanonicalFaceSplitX(",
            "_clipPairedPolygonToXRange(",
            "rectoVersoOverlap",
        ):
            if marker not in partition_text:
                violations.append(
                    f"{PARTITION_PATH.relative_to(ROOT)}: missing `{marker}`; "
                    "BACK partition must transport source area points together "
                    "with sheet-local paint geometry."
                )
        for forbidden_marker in (
            "class BackwardSheetPartition",
            "BackwardSheetPartitionInput",
            "_backwardContinuousFoldEdgeLimitGeometry(",
            "_boundLowAngleVersoPolygon(",
            "_clipPairedPolygonByVerticalX(",
            "back = (localPolygon: sheetLocalPolygon",
            "_synthesizeRectoLimitBand",
            "_normalizeFreeEdgeLimitLine",
            "pageWidth * 1.35",
            "pageWidth * 1.10",
            "limitGeometry.verso.localPolygon",
            "versoRevealWidthNormalized",
        ):
            if forbidden_marker in partition_text:
                violations.append(
                    f"{PARTITION_PATH.relative_to(ROOT)}: old BACK partition/budget "
                    f"marker `{forbidden_marker}` must stay removed."
                )
        for forbidden_marker in (
            "if (leafFrameGeometry != null) {\n    return leafFrameGeometry;",
            "leafFrameGeometry.rectoArea.isNotEmpty",
            "_resolveBackwardLeafFramePairedFaceGeometry(",
            "return leafFrameGeometry;",
        ):
            if forbidden_marker in partition_text:
                violations.append(
                    f"{PARTITION_PATH.relative_to(ROOT)}: BACK low-angle partition "
                    f"must not keep leaf-frame takeover marker `{forbidden_marker}`."
                )
    else:
        violations.append(f"missing partition resolver: {PARTITION_PATH.relative_to(ROOT)}")

    if PAGEFLIP_WIDGET_TEST_PATH.exists():
        widget_test = _strip_comments(
            PAGEFLIP_WIDGET_TEST_PATH.read_text(encoding="utf-8")
        )
        for forbidden_marker in (
            "pageWidth * 1.35",
            "pageWidth * 1.10",
            "pageSize.width * 0.92",
        ):
            if forbidden_marker in widget_test:
                violations.append(
                    f"{PAGEFLIP_WIDGET_TEST_PATH.relative_to(ROOT)}: BACK zero/low-angle "
                    f"test marker `{forbidden_marker}` is a relaxed threshold and must "
                    "not return."
                )
        for marker in (
            "narrowFrontSamples",
            "fullSheetBackSamples",
            "sheetRectoFrontBounds",
            "sheetPaintedUnionBounds",
        ):
            if marker not in widget_test:
                violations.append(
                    f"{PAGEFLIP_WIDGET_TEST_PATH.relative_to(ROOT)}: missing `{marker}`; "
                    "BACK screenshot regression tests must reject recto collapse, "
                    "full-sheet verso, and current-underlay leaks."
                )

    for path in (HOST_PATH, DEBUG_MAPPER_PATH, SOFT_GEOMETRY_PATH):
        if not path.exists():
            continue
        text_for_width = _strip_comments(path.read_text(encoding="utf-8"))
        if "versoRevealWidthNormalized:" in text_for_width:
            violations.append(
                f"{path.relative_to(ROOT)}: BACK partition/painter path must not pass "
                "`versoRevealWidthNormalized:` into geometry partitioning."
            )

    back_band_body = _extract_method_body(
        text,
        r"Widget\s+_buildBackwardBackFoldBandSurface\([^)]*\)\s*\{",
    )
    if back_band_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse "
            "`_buildBackwardBackFoldBandSurface` body"
        )
    else:
        if "_buildBackwardVersoTextureSurface(" not in back_band_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back fold band must use "
                "the explicit verso texture surface instead of the front/recto path."
            )
        if "_validBackPageTextureSnapshotForIndex(" not in back_band_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back fold band must bind "
                "a semantic-back validated previous/flipping leafVerso snapshot before painting."
            )
        if "_buildFlippingSurfaceOverlay(" not in back_band_body or "showBackside: true" not in back_band_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back fold band must reuse "
                "the backside overlay semantics instead of looking like a front page."
            )
        if "ArticlePageSurfaceKind.front" in back_band_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back fold band must not "
                "draw a front page surface."
            )
    if "_buildBackwardFrontFlatLayer(" in text or "backwardFrontFlatPolygon(" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK must not restore the free "
            "previous-front flat paint branch; previous front is owned by the "
            "partitioned moving sheet recto source."
        )
    validator_body = _extract_method_body(
        text,
        r"ArticlePageTextureSnapshot\?\s+_validBackPageTextureSnapshotForIndex\([^)]*\)\s*\{",
    )
    if validator_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back must define "
            "`_validBackPageTextureSnapshotForIndex` for semantic snapshot validation."
        )
    else:
        if "semanticSurfaceKind == ArticlePageSurfaceKind.back.name" not in validator_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK previous-back snapshot validator must "
                "reject same-size snapshots unless `semanticSurfaceKind` is `back`."
            )
    texture_body = _extract_method_body(
        text,
        r"Widget\s+_buildBackwardVersoTextureSurface\([^)]*\)\s*\{",
    )
    if texture_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse "
            "`_buildBackwardVersoTextureSurface` body"
        )
    else:
        if "foldCenterX" in texture_body or "foldLine" in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must mirror in "
                "page-space, not around the moving foldLine."
            )
        if "RawImage(" in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture mainline must not use "
                "RawImage fallback; host and probes must share the same painter."
            )
        if "_BackwardLeafVersoUvPainter" not in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture mainline must route "
                "through `_BackwardLeafVersoUvPainter`."
            )
        if "buildBackwardLeafVersoMaterialUvMesh(" not in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must validate "
                "the fixed material-domain UV mesh, not a dynamic source-area mesh."
            )
        if "buildBackwardLeafVersoPairedUvMesh(" in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must not validate "
                "or paint from `buildBackwardLeafVersoPairedUvMesh`; host paint "
                "must keep material-domain UV fixed and clip by display polygon."
            )
        if "leafVersoSnapshot" not in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must source "
                "the previous/flipping leafVerso snapshot."
            )
        if "article_backward_leaf_verso_texture_wait" not in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK missing-snapshot state must wait "
                "diagnostically instead of rendering a fake mirrored backface."
            )
        if "_buildOpaqueBackPageSurface(" in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture mainline must not "
                "directly render the old opaque mirrored widget path."
            )
        if "mirrorContent: false" in texture_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: BACK verso texture must not render "
                "a front-oriented fallback."
            )
    if "Widget _buildBackwardVersoTextureFallback" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK backBand must not keep a visual "
            "fallback branch that can draw the wrong texture."
        )
    if "_buildBackwardVersoTextureSurface" not in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: missing `_buildBackwardVersoTextureSurface`; "
            "BACK backBand needs one explicit semantic-back snapshot path."
        )
    else:
        texture_surface_body = text[text.find("_buildBackwardVersoTextureSurface") :]
        for marker in ("_BackwardLeafVersoUvPainter",):
            if marker not in texture_surface_body:
                violations.append(
                    f"{HOST_PATH.relative_to(ROOT)}: `_buildBackwardVersoTextureSurface` "
                    f"missing `{marker}` required for shared visible semantic-back texture."
                )
        if "paintBackwardLeafVersoSurface(" not in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: host painter missing "
                "`paintBackwardLeafVersoSurface(` required for shared visible semantic-back texture."
            )
    source_polygon_body = _extract_method_body(
        text,
        r"List<Offset>\s+visibleMovingSheetSourcePolygon\([^)]*\)\s*\{",
    )
    if source_polygon_body is not None:
        for forbidden in (
            "sourceBounds",
            "clipBounds",
            ".intersect(",
        ):
            if forbidden in source_polygon_body:
                violations.append(
                    f"{HOST_PATH.relative_to(ROOT)}: BACK diagnostics must not "
                    f"use bounds fallback `{forbidden}` to mark an unclipped moving "
                    "sheet source as visible."
                )
    uv_mesh_path = (
        APP_LIB
        / "ui"
        / "content"
        / "article_reader"
        / "pageflip"
        / "layers"
        / "backward_leaf_verso_uv_mesh.dart"
    )
    uv_pixel_probe_path = (
        APP_LIB
        / "ui"
        / "content"
        / "article_reader"
        / "pageflip"
        / "layers"
        / "backward_leaf_verso_pixel_probe.dart"
    )
    if not uv_mesh_path.exists():
        violations.append(f"missing BACK leafVerso UV mesh: {uv_mesh_path.relative_to(ROOT)}")
    else:
        uv_mesh_text = _strip_comments(uv_mesh_path.read_text(encoding="utf-8"))
        for marker in (
            "BackwardLeafVersoUvMesh",
            "ui.Vertices.raw(",
            "textureCoordinates: textureValues",
            "buildBackwardLeafVersoMaterialUvMesh(",
            "required List<Offset> materialLocalPolygon",
            "Offset(materialX, materialY)",
        ):
            if marker not in uv_mesh_text:
                violations.append(
                    f"{uv_mesh_path.relative_to(ROOT)}: missing `{marker}` required "
                    "for fixed material-domain BACK verso UV."
                )
        if "textureCoordinate: areaPolygon[index]" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: BACK material UV must not use "
                "the per-frame visible area polygon as texture coordinates."
            )
        if "_backwardVersoAreaPolygon(" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: forbidden dynamic visible-clip "
                "mirror helper in material UV mesh."
            )
        if "textureCoordinates.add(localPoint)" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: BACK leafVerso mesh must not "
                "derive UV from paint-local geometry; consume source area points."
            )
        if "pageSize.width - localPoint.dx" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: BACK leafVerso UV must not "
                "mirror an already mirrored semantic back snapshot a second time."
            )
        if "pageSize.width - materialX" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: BACK verso material UV must "
                "preserve material-local X for the angled baseline; do not "
                "reintroduce the failed extra X reversal."
            )
        if "sourceBounds:" in uv_mesh_text or "sourceBounds" in uv_mesh_text:
            violations.append(
                f"{uv_mesh_path.relative_to(ROOT)}: BACK leafVerso UV must not "
                "normalize texture coordinates from the current visible polygon bounds."
            )
        for forbidden in (
            "backwardVersoTexturePoint(",
            "BackwardVersoTextureDomain",
            "backwardVersoTextureHorizontalInset",
            "sheetBounds:",
            "textureBounds:",
            "0.35",
            "0.65",
        ):
            if forbidden in uv_mesh_text:
                violations.append(
                    f"{uv_mesh_path.relative_to(ROOT)}: forbidden stable-band UV marker "
                    f"`{forbidden}`; BACK verso UV must be source area points."
                )
    if not uv_pixel_probe_path.exists():
        violations.append(
            f"missing BACK leafVerso painter: {uv_pixel_probe_path.relative_to(ROOT)}"
        )
    else:
        uv_pixel_probe_text = _strip_comments(
            uv_pixel_probe_path.read_text(encoding="utf-8")
        )
        for marker in (
            "paintBackwardLeafVersoSurface(",
            "buildBackwardLeafVersoMaterialUvMesh(",
            "required List<Offset> materialLocalPolygon",
            "canvas.drawVertices(",
            "canvas.clipPath(path, doAntiAlias: false)",
        ):
            if marker not in uv_pixel_probe_text:
                violations.append(
                    f"{uv_pixel_probe_path.relative_to(ROOT)}: missing `{marker}` required "
                    "for the shared BACK semantic-back material-locked UV painter."
                )
        if "buildBackwardLeafVersoPairedUvMesh(" in uv_pixel_probe_text:
            violations.append(
                f"{uv_pixel_probe_path.relative_to(ROOT)}: BACK pixel probe/painter must "
                "not call paired display/source UV for the main path; it must keep "
                "fixed material-domain UV and clip by display polygon."
            )
        paint_body = _extract_method_body(
            uv_pixel_probe_text,
            r"void\s+paintBackwardLeafVersoSurface\([^)]*\)\s*\{",
        )
        if paint_body is None:
            violations.append(
                f"{uv_pixel_probe_path.relative_to(ROOT)}: failed to parse "
                "`paintBackwardLeafVersoSurface` body"
            )
        elif "canvas.drawImageRect(" in paint_body:
            violations.append(
                f"{uv_pixel_probe_path.relative_to(ROOT)}: `paintBackwardLeafVersoSurface` "
                "must not regress to `canvas.drawImageRect(...)` as the main UV path."
            )
        draw_vertices_body = _extract_method_body(
            uv_pixel_probe_text,
            r"ui\.Vertices\s+_buildBackwardVersoDrawVertices\([^)]*\)\s*\{",
        )
        if draw_vertices_body is None:
            violations.append(
                f"{uv_pixel_probe_path.relative_to(ROOT)}: failed to parse "
                "`_buildBackwardVersoDrawVertices` body"
            )
        else:
            if "mesh.paintBounds" in draw_vertices_body:
                violations.append(
                    f"{uv_pixel_probe_path.relative_to(ROOT)}: BACK verso UV "
                    "must not rescale the semantic snapshot from `mesh.paintBounds`; "
                    "consume mesh.textureCoordinates from source-paper UV."
                )
            if "mesh.textureCoordinates[index]" not in draw_vertices_body:
                violations.append(
                    f"{uv_pixel_probe_path.relative_to(ROOT)}: BACK verso drawVertices "
                    "must consume the mesh's stable textureCoordinates."
                )
    for path in (uv_mesh_path, uv_pixel_probe_path, HOST_PATH):
        if not path.exists():
            continue
        source_paper_text = _strip_comments(path.read_text(encoding="utf-8"))
        for forbidden in (
            "BackwardVersoTextureDomain",
            "backwardVersoTexturePoint",
            "backwardVersoTextureHorizontalInset",
            "semanticBackSnapshotUvSheetStableBand",
            "sheetBounds:",
            "textureBounds:",
        ):
            if forbidden in source_paper_text:
                violations.append(
                    f"{path.relative_to(ROOT)}: forbidden retired stable-band marker "
                    f"`{forbidden}`; BACK UV must stay source-paper based."
                )
    uv_mapping_path = (
        APP_LIB
        / "ui"
        / "content"
        / "article_reader"
        / "pageflip"
        / "layers"
        / "backward_leaf_verso_texture_mapping.dart"
    )
    if uv_mapping_path.exists():
        violations.append(
            f"{uv_mapping_path.relative_to(ROOT)}: retired stable-band UV mapper "
            "must stay deleted; UV is now carried as source area points."
        )
    for marker in (
        "backwardVersoDisplayState",
        "backwardVersoTextureUvStrategy",
        "materialLockedUv",
        "backwardFrontBackOverlapWidth",
        "backwardBackVisibleUncoveredWidth",
        "backwardBackVisibleProbeCount",
        "backwardPaintSources",
        "backwardVersoProbeViewportPoints",
        "paperFallback",
        "semanticSnapshot",
    ):
        if marker not in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: missing `{marker}` required "
                "for BACK visible-texture diagnostics and framebuffer acceptance."
            )
    if "sourceAreaPointUv" in text:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: BACK diagnostics must not accept "
            "`sourceAreaPointUv`; dynamic source-area UV was the texture-scanning regression."
        )
    diagnostics_path = APP_LIB / "components" / "pageflip" / "src" / "debug" / "pageflip_diagnostics.dart"
    if diagnostics_path.exists():
        diagnostics_text = _strip_comments(diagnostics_path.read_text(encoding="utf-8"))
        for marker in (
            "label: 'tex'",
            "label: 'overlap'",
            "label: 'sources'",
            "backwardVersoDisplayState",
        ):
            if marker not in diagnostics_text:
                violations.append(
                    f"{diagnostics_path.relative_to(ROOT)}: missing `{marker}` required "
                    "for screenshot-visible BACK texture and overlap diagnostics."
                )
    else:
        violations.append(f"missing diagnostics overlay: {diagnostics_path.relative_to(ROOT)}")
    for marker in (
        "staticCurrentFront",
        "bottomCurrentFront",
        "sheetRectoFront",
        "sheetVersoBack",
        "foldOverlay",
    ):
        if marker not in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: missing BACK paint source marker `{marker}` "
                "required for source-attributed color-block debugging."
            )
    for marker in (
        "previousFrontFlatUnifiedToBack",
        "sheetRectoUnifiedToBack",
        "status: 'unifiedToBack'",
    ):
        if marker in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: forbidden unified-back source marker `{marker}`; "
                "BACK recto/front and verso/back diagnostics must remain separate."
            )
    texture_path = APP_LIB / "ui" / "content" / "pageflip" / "page_surface_snapshot.dart"
    if texture_path.exists():
        texture_text = _strip_comments(texture_path.read_text(encoding="utf-8"))
        binding_body = _extract_method_body(
            texture_text,
            r"ArticlePageTextureBinding\?\s+resolveArticlePageTextureBinding\([^)]*\)\s*\{",
        )
        if binding_body is not None:
            back_return = binding_body.rfind("return ArticlePageTextureBinding(")
            back_body = binding_body[back_return:] if back_return >= 0 else binding_body
            if "rectoPageIndex: flippingPageIndex" not in back_body:
                violations.append(
                    f"{texture_path.relative_to(ROOT)}: BACK recto must remain the "
                    "flipping previous page."
                )
            if "versoPageIndex: flippingPageIndex" not in back_body:
                violations.append(
                    f"{texture_path.relative_to(ROOT)}: BACK verso/back texture must use "
                    "the flipping previous page, matching the physical leaf."
                )
            if "versoPageIndex: currentPageIndex" in back_body:
                violations.append(
                    f"{texture_path.relative_to(ROOT)}: BACK verso/back texture must not use "
                    "the covered current page."
                )
            if "bottomPageIndex: currentPageIndex" not in back_body:
                violations.append(
                    f"{texture_path.relative_to(ROOT)}: BACK bottom must remain the "
                    "covered current page."
                )
    return violations


def _check_backward_texture_binding() -> list[str]:
    violations: list[str] = []
    snapshot_path = APP_LIB / "ui" / "content" / "pageflip" / "page_surface_snapshot.dart"
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
        "- (2 * localPagePoint.dx)",
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
