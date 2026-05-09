#!/usr/bin/env python3
"""Static gate for the BACK pageflip mainline (native StPageFlip BACK).

This script enforces the architectural rules in
`.cursor/rules/12-pageflip-backward-mainline.mdc`:

1. Forbidden symbols (retired resolvers, host bypass branches, projected-frame
   polygon fields, deprecated soft helpers) must not exist anywhere under
   `quwoquan_app/lib/ui/content/...`.
2. The retired full-page previous-front baseline
   `ValueKey('article_backward_previous_front_baseline')` must not exist in lib.
3. The native BACK invariant must hold:
   - `backward_render_frame_builder.dart` must not recreate a forward
     calculation or X-mirror geometry.
   - `routeBSpineMirroredApplied:` must remain surfaced as a diagnostic flag
     and be false on the native BACK path.
4. `_localPolygonFromArea` MUST contain the StPageFlip BACK drawSoft formula
   `anchor.dx - point.dx`, while forward keeps `point.dx - anchor.dx`.
5. BACK flipping sheet must split recto/front and verso/back inside the same
   soft surface; diagnostics must expose both polygons from the same geometry.
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

ROOT = Path(__file__).resolve().parents[1]
APP_LIB = ROOT / "quwoquan_app" / "lib"

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
RENDER_FRAME_PATH = APP_LIB / "ui" / "content" / "pageflip" / "render_frame.dart"
RENDER_FRAME_BUILDER_PATH = (
    APP_LIB / "ui" / "content" / "pageflip" / "backward_render_frame_builder.dart"
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
    # Route B (M1) cutover: BACK soft helper / display-position resolver are
    # all retired. Frame builder X-mirrors area/anchor/angle and BACK reuses
    # forward path; no separate BACK soft geometry helper may exist.
    "_resolveBackwardDisplayPosition",
    "resolveBackwardSoftPageGeometry",
)

# Forbidden polygon fields on ArticlePageBackwardProjectedFrame.
FORBIDDEN_PROJECTED_FRAME_FIELDS = (
    "previousFoldSurfacePolygon",
    "previousBackFoldPolygon",
    "previousFrontFoldPolygon",
    "currentResidualPolygon",
)

BASELINE_VALUE_KEY = "'article_backward_previous_front_baseline'"

# Required strings inside backward_render_frame_builder.dart. Native BACK must
# preserve the BACK calculation output and surface the diagnostic flag.
REQUIRED_FRAME_BUILDER_STRINGS = (
    "flippingClipArea = data.flippingClipArea",
    "flippingAnchor = data.flippingAnchor",
    "angle: data.angle",
    "routeBSpineMirroredApplied:",
)

FORBIDDEN_FRAME_BUILDER_STRINGS = (
    "_runForwardEquivalentCalc(",
    "_ForwardEquivalentGeometry",
    "_mirrorAreaX(",
    "_mirrorX(",
    "StPageFlipCalculation(\n    direction: StPageFlipDirection.forward",
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


def _check_frame_builder_native_back() -> list[str]:
    """Frame builder must preserve native BACK calculation outputs.

    The failed frame-mirror path recreated a forward calculation and X-mirrored
    it, producing negative viewport coordinates in Flutter. Native BACK keeps
    `data.flippingClipArea / activeCorner / angle` and lets the host apply the
    StPageFlip direction-aware `drawSoft` formula.
    """

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
                "BACK frame builder must preserve native BACK calculation output."
            )
    for forbidden in FORBIDDEN_FRAME_BUILDER_STRINGS:
        if forbidden in builder:
            violations.append(
                f"{RENDER_FRAME_BUILDER_PATH.relative_to(ROOT)}: forbidden native-BACK regression marker `{forbidden}`. "
                "Do not recreate a forward calculation or X-mirror BACK geometry."
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

    poly_body = _extract_method_body(
        text,
        r"List<Offset>\s+_localPolygonFromArea\([^)]*\)\s*\{",
    )
    if poly_body is None:
        violations.append(
            f"{HOST_PATH.relative_to(ROOT)}: failed to parse `_localPolygonFromArea` body"
        )
    else:
        if "direction == StPageFlipDirection.back" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPolygonFromArea` must contain the "
                "native StPageFlip BACK branch."
            )
        if "anchor.dx - point.dx" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPolygonFromArea` must implement "
                "`anchor.dx - point.dx` for BACK drawSoft."
            )
        if "point.dx - anchor.dx" not in poly_body:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: `_localPolygonFromArea` must keep "
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
        "_buildBackwardRectoVersoFlippingPageSurface(",
        "_buildBackwardSheetFaceSlice(",
        "_backwardPageIntervalToClipRect(",
        "backwardLeafFrame: frame.backwardLeafFrame",
        "ArticlePageSurfaceKind.front",
        "ArticlePageSurfaceKind.back",
        "Rect.fromLTWH(",
        "clipBehavior: Clip.none",
        "previousFrontLocalPolygon",
        "previousBackLocalPolygon",
        "transformSoftLayerLocalPolygon(",
    )
    for marker in required_markers:
        if marker not in text:
            violations.append(
                f"{HOST_PATH.relative_to(ROOT)}: missing recto/verso BACK split marker `{marker}`. "
                "BACK must split previous-front and previous-back inside one moving sheet."
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
                "`versoPageIndex: flippingPageIndex`."
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
                "return the active direction (native BACK invariant)."
            )
    return violations


def _check_projected_frame_fields() -> list[str]:
    violations: list[str] = []
    if not RENDER_FRAME_PATH.exists():
        violations.append(f"missing render frame: {RENDER_FRAME_PATH.relative_to(ROOT)}")
        return violations
    rf = _strip_comments(RENDER_FRAME_PATH.read_text(encoding="utf-8"))
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


def main() -> int:
    if not APP_LIB.exists():
        print(f"pageflip_backward_mainline: FAIL missing {APP_LIB}", file=sys.stderr)
        return 1

    violations: list[str] = []
    violations.extend(_check_forbidden_symbols())
    violations.extend(_check_no_previous_front_baseline())
    violations.extend(_check_frame_builder_native_back())
    violations.extend(_check_native_back_draw_soft_in_host_helpers())
    violations.extend(_check_recto_verso_split_in_host())
    violations.extend(_check_backward_texture_binding())
    violations.extend(_check_soft_geometry_helper_clean())
    violations.extend(_check_projected_frame_fields())

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
