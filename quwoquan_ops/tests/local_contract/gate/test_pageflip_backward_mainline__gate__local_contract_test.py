"""local_contract: BACK 翻页主线门禁的正负例。

门禁只有 `main()` 一个入口，扫描面全部由 import 期固化的模块级路径常量决定。不改门禁
本身就只剩一条路：把这些常量临时重绑到 tempfile 合成的 Dart 树上，逐条判据构造「干净
样本被接受 / 违规样本被拒绝」。只断言真实仓库是绿的无法证明判据还在生效——判据被写坏成
恒真时，全仓扫描同样是绿的。

合成 Dart 片段只保留门禁真正读的那几个标记，不追求可编译：门禁是静态文本判定，多余的
上下文只会让「这条判据到底在钉什么」变得不可读。
"""

from __future__ import annotations

import contextlib
import importlib.util
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    ROOT
    / "quwoquan_app/scripts/content_service/content/post"
    / "verify_pageflip_backward_mainline.py"
)

_HOST_DIR_RELATIVE = (
    "quwoquan_app/lib/service/content_service/content/post/presentation"
    "/article_reader/pageflip/host"
)
_HOST_STEM = "article_read_only_book_deck"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_pageflip_backward_mainline", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _rebound(module, **attributes) -> Iterator[None]:
    """临时重绑门禁的模块级路径常量，退出时无条件还原。

    每个用例都重新加载模块，但仍然还原：一个用例改坏常量后让后续用例扫到半棵合成树，
    失败信息会指向完全无关的判据。
    """

    original = {name: getattr(module, name) for name in attributes}
    for name, value in attributes.items():
        setattr(module, name, value)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(module, name, value)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# 唯一保留的 BACK 局部裁剪公式：verso 用 `anchor.dx - point.dx`，forward 保持
# `point.dx - anchor.dx`。UV 取全幅材质坐标，`flippingClipArea` 只当裁剪窗口用。
_HOST_SOFT_HELPERS = """
Widget _buildSoftPageLayer(ArticlePageRenderFrame frame) {
  final useBackwardMaterialSheet =
      frame.direction == StPageFlipDirection.back;
  final sheetMaterialLocalPolygon = pageRectPolygon(pageSize);
  return _buildSoftFlippingPageSurface(
    materialLocalPolygon: sheetMaterialLocalPolygon,
    useBackwardMaterialSheet: useBackwardMaterialSheet,
  );
}

Offset _localPointFromAreaPoint(
  Offset point,
  Offset anchor,
  StPageFlipDirection direction,
) {
  if (direction == StPageFlipDirection.back) {
    return Offset(anchor.dx - point.dx, point.dy - anchor.dy);
  }
  return Offset(point.dx - anchor.dx, point.dy - anchor.dy);
}
"""

_FRAME_BUILDER = """
ArticlePageBackwardProjectedFrame buildBackwardRenderFrame(
  StPageFlipCalculationInput input,
) {
  final visualGeometry = _resolveBackwardVisualGeometry(
    resolveBackwardForwardCanonicalPoint(input.point, input.pageWidth),
  );
  return ArticlePageBackwardProjectedFrame(
    direction: StPageFlipDirection.forward,
    visualGeometryDirection: visualGeometry.direction,
    foldLineSource: 'backwardForwardIsomorphicFoldLine',
    edgeLineSource: 'backwardForwardIsomorphicFreeEdgeLine',
    routeBSpineMirroredApplied: visualGeometry.spineMirrored,
  );
}
"""

# L0 先铺 current 底页，L1 再铺唯一一张会动的分裂纸——顺序反了就等于 BACK 又回到
# 「整页替换」的旧架构。
_DYNAMIC_LAYERS = """
ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers(
  ArticleReadOnlyBookScene scene,
  ArticlePageRenderFrame frame,
  ArticlePageTextureBinding? textureBinding,
  int flippingPageIndex,
) {
  final underlay = _buildStaticPageLayer(
    pageIndex: scene.bottomPageIndex!,
  );
  final moving = _buildBackwardSplitFlippingSurface(
    clipArea: frame.flippingClipArea,
    pageIndex: flippingPageIndex,
    backFacePageIndex: textureBinding?.versoPageIndex,
    backwardLeafFrame: frame.backwardLeafFrame,
  );
  return ArticleReadOnlyBookRenderBranch(
    layers: <Widget>[underlay, moving],
  );
}
"""

# recto/verso 由 StPageFlip 的 F/E/clip 几何一次解出，两面同属一张 soft sheet；
# 用 progress 阈值选面会在临界点抖出整页闪烁。
_SOFT_LAYERS = """
Widget _buildBackwardSplitFlippingSurface(
  ArticlePageBackwardLeafFrame backwardLeafFrame,
) {
  final faces = resolveBackwardCanonicalSheetFaces(
    BackwardCanonicalSheetInput(
      rectoCoverage: backwardLeafFrame.sheetRectoCoverageNormalized,
    ),
  );
  return Stack(
    children: <Widget>[
      _buildBackwardSheetFacePolygon(
        key: const ValueKey<String>('article_backward_flipping_recto_slice'),
        kind: ArticlePageSurfaceKind.front,
        polygon: faces.recto,
      ),
      _buildBackwardSheetFacePolygon(
        key: const ValueKey<String>('article_backward_flipping_verso_slice'),
        kind: ArticlePageSurfaceKind.back,
        polygon: faces.verso,
      ),
    ],
  );
}

Widget _buildSoftPageLayer(ArticlePageRenderFrame frame) {
  return Transform.rotate(
    angle: frame.angle,
    child: ClipPath(
      clipper: ArticleSheetClipper(frame.clipPolygon),
      child: Transform.translate(
        offset: -paintOrigin,
        child: _buildSoftFlippingPageSurface(frame),
      ),
    ),
  );
}
"""

_DIAGNOSTIC_GEOMETRY = """
ArticleBackwardSheetFaces debugBackwardSheetFaces(
  ArticlePageBackwardLeafFrame backwardLeafFrame,
) {
  return resolveBackwardCanonicalSheetFaces(
    BackwardCanonicalSheetInput(
      rectoCoverage: backwardLeafFrame.sheetRectoCoverageNormalized,
    ),
  );
}
"""

# forward 分支合法地用 currentPageIndex 当 verso；门禁只约束最后一个 return，
# 也就是 BACK 分支——把这两个分支写进同一份 fixture 才能钉住这个边界。
_SURFACE_SNAPSHOT = """
class ArticlePageSurfaceSnapshot {
  const ArticlePageSurfaceSnapshot(this.leafPageIndex);

  final int leafPageIndex;

  int get leafVersoPageIndex => leafPageIndex;
}

ArticlePageTextureBinding? resolveArticlePageTextureBinding(
  ArticleReadOnlyBookScene scene,
  int currentPageIndex,
  int flippingPageIndex,
) {
  if (scene.direction == StPageFlipDirection.forward) {
    return ArticlePageTextureBinding(
      versoPageIndex: currentPageIndex,
      bottomPageIndex: flippingPageIndex,
    );
  }
  return ArticlePageTextureBinding(
    versoPageIndex: flippingPageIndex,
    bottomPageIndex: currentPageIndex,
  );
}
"""

# 门禁的 `softLayerViewportDirection` 判据要求方法体后面还有一行；`_strip_comments`
# 会吃掉文件末尾换行，所以合成文件必须像真实文件那样在其后还有内容。
_SOFT_GEOMETRY = """
StPageFlipDirection softLayerViewportDirection(
  StPageFlipDirection direction,
) {
  return direction;
}

Rect softLayerPaintBounds(Rect sheetRect) {
  return sheetRect;
}
"""

# 多边形字段的判据只作用于 ArticlePageBackwardProjectedFrame 一个类；同文件的其他类
# 持有多边形是合法的，因此 fixture 必须有第二个类来暴露作用域边界。
_RENDER_FRAME = """
class ArticlePageBackwardProjectedFrame {
  const ArticlePageBackwardProjectedFrame({required this.rectoCoverage});

  final double rectoCoverage;
}

class ArticlePageRenderFrame {
  const ArticlePageRenderFrame({required this.flippingClipArea});

  final List<Offset> flippingClipArea;
}
"""

# BACK 视觉回放必须从 forward 完成态的负 X 位姿起步，因此保留 `-pageWidth` 下界与
# `2 * pageWidth * visualProgress` 的行程；把 X 夹到 0..pageWidth 会把起手位姿抹平。
_GEOMETRY = """
Offset resolveBackwardVisualReplayCanonicalPoint(
  double pageWidth,
  double dragProgress,
  double edgeEpsilon,
) {
  final visualProgress = 1.0 - dragProgress;
  final x = pageWidth - edgeEpsilon - 2 * pageWidth * visualProgress;
  return Offset(x < -pageWidth ? -pageWidth : x, 0.0);
}
"""


class PageflipBackwardMainlineGateTest(unittest.TestCase):
    def test_forbidden_symbol_is_rejected_in_code_and_exempt_in_doc_comment(
        self,
    ) -> None:
        """退役符号的判定对象是可执行代码：文档注释要能解释为什么它被删掉。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pageflip = root / "quwoquan_app/lib/design_system/pageflip"
            target = pageflip / "layers.dart"
            with _rebound(module, ROOT=root, UI_PAGEFLIP_DIRS=[pageflip]):
                _write(
                    target,
                    "Offset resolveBackwardSoftPageGeometry(Offset point) {\n"
                    "  return point;\n"
                    "}\n",
                )
                violations = module._check_forbidden_symbols()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("resolveBackwardSoftPageGeometry", violations[0])

                _write(
                    target,
                    "/// resolveBackwardSoftPageGeometry 已随 Route-B 收口删除。\n"
                    "Offset resolveForwardCanonicalPoint(Offset point) {\n"
                    "  return point;\n"
                    "}\n",
                )
                self.assertEqual(module._check_forbidden_symbols(), [])

    def test_full_previous_front_baseline_value_key_is_rejected(self) -> None:
        """整页 previous-front 底板已退役：BACK 的前一页正面只能由动纸内的 recto 切片画。

        这条判据刻意不剥注释——ValueKey 字面量一旦还留在文件里，就说明对应图层随时能被
        重新挂回去。
        """

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pageflip = root / "quwoquan_app/lib/design_system/pageflip"
            target = pageflip / "layers.dart"
            with _rebound(module, ROOT=root, UI_PAGEFLIP_DIRS=[pageflip]):
                _write(
                    target,
                    "const ValueKey<String>"
                    "('article_backward_previous_front_baseline');\n",
                )
                self.assertEqual(len(module._check_no_previous_front_baseline()), 1)

                _write(
                    target,
                    "// const ValueKey<String>"
                    "('article_backward_previous_front_baseline');\n",
                )
                self.assertEqual(len(module._check_no_previous_front_baseline()), 1)

                _write(
                    target,
                    "const ValueKey<String>"
                    "('article_backward_flipping_recto_slice');\n",
                )
                self.assertEqual(module._check_no_previous_front_baseline(), [])

    def test_retired_backward_leaf_renderer_file_must_stay_deleted(self) -> None:
        """BACK 只走单一 forward 同构的 vertices/UV 路径，第二套渲染器不得复活。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            retired = (
                root
                / "quwoquan_app/lib/design_system/pageflip/backward_leaf_renderer.dart"
            )
            with _rebound(
                module, ROOT=root, OLD_BACKWARD_LEAF_RENDERER_PATH=retired
            ):
                self.assertEqual(
                    module._check_no_retired_backward_leaf_renderer(), []
                )
                _write(retired, "class ArticlePageBackwardLeafRenderer {}\n")
                violations = module._check_no_retired_backward_leaf_renderer()
                self.assertEqual(len(violations), 1, msg=f"{violations}")

    def test_host_part_declarations_must_match_the_host_directory(self) -> None:
        """host library 的 part 必须与目录内容一一对应，孤儿 part 会绕开全部 host 判据。"""

        module = _load_module()
        for name, host_source, extra_files, expected in (
            (
                "declared_part_missing",
                f"part '{_HOST_STEM}_soft_layers.dart';\n",
                {},
                "declared part",
            ),
            (
                "orphan_deck_part",
                "",
                {f"{_HOST_STEM}_soft_layers.dart": "// 未被 host 声明\n"},
                "is not declared by",
            ),
            (
                "duplicate_declaration",
                f"part '{_HOST_STEM}_soft_layers.dart';\n"
                f"part '{_HOST_STEM}_soft_layers.dart';\n",
                {f"{_HOST_STEM}_soft_layers.dart": "// part\n"},
                "duplicate part declaration",
            ),
            (
                "part_outside_host_directory",
                f"part 'legacy/{_HOST_STEM}_soft_layers.dart';\n",
                {f"legacy/{_HOST_STEM}_soft_layers.dart": "// part\n"},
                "must stay in the host directory",
            ),
        ):
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
                    _write(host, host_source)
                    for relative, text in extra_files.items():
                        _write(host.parent / relative, text)
                    with _rebound(module, ROOT=root, HOST_PATH=host):
                        violations = module._check_host_library_parts()
                        self.assertEqual(len(violations), 1, msg=f"{violations}")
                        self.assertIn(expected, violations[0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
            _write(host, f"part '{_HOST_STEM}_soft_layers.dart';\n")
            _write(host.parent / f"{_HOST_STEM}_soft_layers.dart", "// part\n")
            with _rebound(module, ROOT=root, HOST_PATH=host):
                self.assertEqual(module._check_host_library_parts(), [])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
            with _rebound(module, ROOT=root, HOST_PATH=host):
                violations = module._check_host_library_parts()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("missing host", violations[0])

    def test_frame_builder_keeps_semantic_back_on_forward_isomorphic_geometry(
        self,
    ) -> None:
        """BACK 语义与 forward 同构视觉几何必须同时在场；退役的镜像 helper 不得回归。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            builder = (
                root
                / "quwoquan_app/lib/design_system/pageflip"
                / "backward_render_frame_builder.dart"
            )
            with _rebound(module, ROOT=root, RENDER_FRAME_BUILDER_PATH=builder):
                violations = module._check_frame_builder_native_back()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("missing builder", violations[0])

                _write(builder, _FRAME_BUILDER)
                self.assertEqual(module._check_frame_builder_native_back(), [])

                _write(
                    builder,
                    _FRAME_BUILDER.replace(
                        "    routeBSpineMirroredApplied: visualGeometry.spineMirrored,\n",
                        "",
                    ),
                )
                violations = module._check_frame_builder_native_back()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("routeBSpineMirroredApplied:", violations[0])

                _write(
                    builder,
                    _FRAME_BUILDER.replace(
                        "  final visualGeometry = _resolveBackwardVisualGeometry(",
                        "  final mirrored = _mirrorAreaX(input.area);\n"
                        "  final visualGeometry = _resolveBackwardVisualGeometry(",
                    ),
                )
                violations = module._check_frame_builder_native_back()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("_mirrorAreaX(", violations[0])

    def test_back_draw_soft_formula_and_material_locked_uv_are_pinned(self) -> None:
        """BACK 只能以 `anchor.dx - point.dx` 存在于局部裁剪公式里，UV 走全幅材质坐标。"""

        module = _load_module()
        for name, host_source, expected in (
            (
                "missing_back_formula",
                _HOST_SOFT_HELPERS.replace(
                    "anchor.dx - point.dx", "point.dx - anchor.dx"
                ),
                "`anchor.dx - point.dx` for BACK drawSoft",
            ),
            (
                "missing_forward_formula",
                _HOST_SOFT_HELPERS.replace(
                    "return Offset(point.dx - anchor.dx, point.dy - anchor.dy);",
                    "return Offset(anchor.dx - point.dx, point.dy - anchor.dy);",
                ),
                "`point.dx - anchor.dx` for FORWARD drawSoft",
            ),
            (
                "deprecated_soft_helper_call",
                _HOST_SOFT_HELPERS.replace(
                    "  final sheetMaterialLocalPolygon = pageRectPolygon(pageSize);",
                    "  final sheetMaterialLocalPolygon = pageRectPolygon(pageSize);\n"
                    "  resolveBackwardSoftPageGeometry(frame);",
                ),
                "deprecated `resolveBackwardSoftPageGeometry`",
            ),
            (
                "uv_from_dynamic_visible_clip",
                _HOST_SOFT_HELPERS.replace(
                    "    materialLocalPolygon: sheetMaterialLocalPolygon,",
                    "    materialLocalPolygon: polygon,",
                ),
                "BACK UV cannot be derived from the dynamic visible clip",
            ),
            (
                "sheet_area_from_moving_window",
                _HOST_SOFT_HELPERS.replace(
                    "    useBackwardMaterialSheet: useBackwardMaterialSheet,",
                    "    sheetAreaPolygon: area,\n"
                    "    useBackwardMaterialSheet: useBackwardMaterialSheet,",
                ),
                "reintroduces texture scanning",
            ),
        ):
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
                    _write(host, host_source)
                    with _rebound(module, ROOT=root, HOST_PATH=host):
                        violations = (
                            module._check_native_back_draw_soft_in_host_helpers()
                        )
                        self.assertEqual(len(violations), 1, msg=f"{violations}")
                        self.assertIn(expected, violations[0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
            _write(host, _HOST_SOFT_HELPERS)
            with _rebound(module, ROOT=root, HOST_PATH=host):
                self.assertEqual(
                    module._check_native_back_draw_soft_in_host_helpers(), []
                )

    def test_moving_sheet_splits_recto_and_verso_from_one_geometry(self) -> None:
        """Route-B：current 底页 + 一张分裂动纸，两面同源于同一份 canonical 几何。"""

        module = _load_module()

        def _build(root: Path) -> Path:
            host = root / _HOST_DIR_RELATIVE / f"{_HOST_STEM}.dart"
            _write(host, "// host library root\n")
            _write(host.parent / f"{_HOST_STEM}_dynamic_layers.dart", _DYNAMIC_LAYERS)
            _write(host.parent / f"{_HOST_STEM}_soft_layers.dart", _SOFT_LAYERS)
            _write(
                host.parent / f"{_HOST_STEM}_diagnostic_geometry.dart",
                _DIAGNOSTIC_GEOMETRY,
            )
            return host

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = _build(root)
            with _rebound(module, ROOT=root, HOST_PATH=host):
                self.assertEqual(module._check_recto_verso_split_in_host(), [])

        for name, patch, expected in (
            (
                "flipping_sheet_painted_before_underlay",
                (
                    f"{_HOST_STEM}_dynamic_layers.dart",
                    _DYNAMIC_LAYERS.replace(
                        "    clipArea: frame.flippingClipArea,\n", ""
                    ).replace(
                        "  final underlay = _buildStaticPageLayer(",
                        "  final clipArea = frame.flippingClipArea;\n"
                        "  final underlay = _buildStaticPageLayer(",
                    ),
                ),
                "must paint current L0 underlay before the flipping L1 sheet",
            ),
            (
                "face_chosen_by_progress",
                (
                    f"{_HOST_STEM}_soft_layers.dart",
                    _SOFT_LAYERS.replace(
                        "  return Stack(",
                        "  if (progress > 0.5) {\n"
                        "    return const SizedBox.shrink();\n"
                        "  }\n"
                        "  return Stack(",
                    ),
                ),
                "must not choose a face from progress",
            ),
            (
                "diagnostics_use_a_second_resolver",
                (
                    f"{_HOST_STEM}_diagnostic_geometry.dart",
                    _DIAGNOSTIC_GEOMETRY.replace(
                        "resolveBackwardCanonicalSheetFaces",
                        "debugResolveSheetFacesLocally",
                    ),
                ),
                "same canonical moving-sheet face resolver as paint",
            ),
        ):
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    host = _build(root)
                    relative, source = patch
                    _write(host.parent / relative, source)
                    with _rebound(module, ROOT=root, HOST_PATH=host):
                        violations = module._check_recto_verso_split_in_host()
                        self.assertEqual(len(violations), 1, msg=f"{violations}")
                        self.assertIn(expected, violations[0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            host = _build(root)
            _write(
                host,
                "const retired = 'article_backward_previous_front_baseline';\n",
            )
            with _rebound(module, ROOT=root, HOST_PATH=host):
                violations = module._check_recto_verso_split_in_host()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("retired BACK replacement", violations[0])

    def test_backward_texture_binding_uses_the_previous_leaf_backside(self) -> None:
        """BACK 的 verso 是前一张叶子的背面，current 只能当 L0 底页。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app_lib = root / "quwoquan_app/lib"
            snapshot = app_lib / "design_system/pageflip/page_surface_snapshot.dart"
            with _rebound(module, ROOT=root, APP_LIB=app_lib):
                _write(snapshot, _SURFACE_SNAPSHOT)
                self.assertEqual(module._check_backward_texture_binding(), [])

                _write(
                    snapshot,
                    _SURFACE_SNAPSHOT.replace(
                        "  return ArticlePageTextureBinding(\n"
                        "    versoPageIndex: flippingPageIndex,",
                        "  return ArticlePageTextureBinding(\n"
                        "    versoPageIndex: currentPageIndex,",
                    ),
                )
                violations = module._check_backward_texture_binding()
                self.assertEqual(len(violations), 2, msg=f"{violations}")
                self.assertTrue(
                    any("versoPageIndex: flippingPageIndex" in v for v in violations)
                )
                self.assertTrue(
                    any(
                        "must not use" in v and "versoPageIndex: currentPageIndex" in v
                        for v in violations
                    )
                )

                _write(
                    snapshot,
                    _SURFACE_SNAPSHOT.replace(
                        "  int get leafVersoPageIndex => leafPageIndex;\n", ""
                    ),
                )
                violations = module._check_backward_texture_binding()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("must resolve to leafPageIndex", violations[0])

    def test_soft_geometry_helper_keeps_no_back_specific_branch(self) -> None:
        """BACK 的镜像收在 frame builder 里；soft 几何模块必须对方向保持中立。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            geometry = (
                root
                / "quwoquan_app/lib/service/content_service/content/post/presentation"
                / "article_reader/pageflip/layers"
                / "article_reader_soft_page_geometry.dart"
            )
            with _rebound(module, ROOT=root, SOFT_GEOMETRY_PATH=geometry):
                violations = module._check_soft_geometry_helper_clean()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("missing soft geometry", violations[0])

                _write(geometry, _SOFT_GEOMETRY)
                self.assertEqual(module._check_soft_geometry_helper_clean(), [])

                _write(
                    geometry,
                    "Offset _resolveBackwardDisplayPosition(Offset point) {\n"
                    "  return point;\n"
                    "}\n" + _SOFT_GEOMETRY,
                )
                violations = module._check_soft_geometry_helper_clean()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("_resolveBackwardDisplayPosition", violations[0])

                _write(
                    geometry,
                    "Offset softLayerViewport(Rect pageViewportRect: bounds) {\n"
                    "  return Offset.zero;\n"
                    "}\n" + _SOFT_GEOMETRY,
                )
                violations = module._check_soft_geometry_helper_clean()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("`pageViewportRect` parameter", violations[0])

                _write(
                    geometry,
                    _SOFT_GEOMETRY.replace(
                        "  return direction;",
                        "  return StPageFlipDirection.forward;",
                    ),
                )
                violations = module._check_soft_geometry_helper_clean()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("must always", violations[0])

    def test_projected_frame_declares_no_polygon_fields(self) -> None:
        """投影帧只携带标量；重新长出多边形字段就意味着 BACK 又有了第二套几何真相源。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pageflip = root / "quwoquan_app/lib/design_system/pageflip"
            render_frame = pageflip / "render_frame.dart"
            builder = pageflip / "backward_render_frame_builder.dart"
            with _rebound(
                module,
                ROOT=root,
                RENDER_FRAME_PATH=render_frame,
                RENDER_FRAME_BUILDER_PATH=builder,
            ):
                _write(render_frame, _RENDER_FRAME)
                _write(builder, _FRAME_BUILDER)
                self.assertEqual(module._check_projected_frame_fields(), [])

                _write(
                    render_frame,
                    _RENDER_FRAME.replace(
                        "  final double rectoCoverage;",
                        "  final double rectoCoverage;\n"
                        "  final List<Offset> previousFoldSurfacePolygon;",
                    ),
                )
                violations = module._check_projected_frame_fields()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("previousFoldSurfacePolygon", violations[0])

                _write(
                    render_frame,
                    _RENDER_FRAME.replace(
                        "  final List<Offset> flippingClipArea;",
                        "  final List<Offset> flippingClipArea;\n"
                        "  final List<Offset> previousFoldSurfacePolygon;",
                    ),
                )
                self.assertEqual(module._check_projected_frame_fields(), [])

                _write(render_frame, _RENDER_FRAME)
                _write(
                    builder,
                    _FRAME_BUILDER.replace(
                        "    routeBSpineMirroredApplied: visualGeometry.spineMirrored,",
                        "    routeBSpineMirroredApplied: visualGeometry.spineMirrored,\n"
                        "    currentResidualPolygon: visualGeometry.residual,",
                    ),
                )
                violations = module._check_projected_frame_fields()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("currentResidualPolygon", violations[0])

                _write(
                    render_frame,
                    _RENDER_FRAME.replace(
                        "  final double rectoCoverage;",
                        "  final double rectoCoverage;\n"
                        "  double get settled =>\n"
                        "      lerpDouble(rectoCoverageByFold, 1.0, t)!;",
                    ),
                )
                _write(builder, _FRAME_BUILDER)
                violations = module._check_projected_frame_fields()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("front-dominant contamination", violations[0])

    def test_backward_visual_replay_starts_from_forward_completed_pose(self) -> None:
        """竖屏 BACK 的起手位姿在负 X 侧；夹紧到 0..pageWidth 会让第一帧直接跳变。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            geometry = root / "quwoquan_app/lib/design_system/pageflip/geometry.dart"
            with _rebound(module, ROOT=root, GEOMETRY_PATH=geometry):
                violations = module._check_backward_visual_replay_mapping()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("missing geometry", violations[0])

                _write(geometry, "// 没有回放映射\n")
                violations = module._check_backward_visual_replay_mapping()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn(
                    "missing resolveBackwardVisualReplayCanonicalPoint", violations[0]
                )

                _write(geometry, _GEOMETRY)
                self.assertEqual(module._check_backward_visual_replay_mapping(), [])

                _write(
                    geometry,
                    _GEOMETRY.replace(
                        "2 * pageWidth * visualProgress", "pageWidth * visualProgress"
                    ),
                )
                violations = module._check_backward_visual_replay_mapping()
                self.assertEqual(len(violations), 1, msg=f"{violations}")
                self.assertIn("2 * pageWidth * visualProgress", violations[0])

                _write(
                    geometry,
                    _GEOMETRY.replace(
                        "  return Offset(x < -pageWidth ? -pageWidth : x, 0.0);",
                        "  return Offset(x.clamp(0.0, pageWidth), 0.0);",
                    ),
                )
                violations = module._check_backward_visual_replay_mapping()
                self.assertEqual(len(violations), 2, msg=f"{violations}")
                self.assertTrue(any("must not clamp visual X" in v for v in violations))

    def test_method_body_extraction_survives_nested_braces(self) -> None:
        """几乎每条判据都靠它切出方法体：括号配平一旦失真，全部判据会一起静默放行。"""

        module = _load_module()
        source = (
            "Offset _localPointFromAreaPoint(Offset point, Offset anchor) {\n"
            "  if (point.dx > anchor.dx) {\n"
            "    return Offset(anchor.dx - point.dx, 0.0);\n"
            "  }\n"
            "  return point;\n"
            "}\n"
            "\n"
            "Offset unrelated() {\n"
            "  return Offset.zero;\n"
            "}\n"
        )
        body = module._extract_method_body(
            source, r"Offset\s+_localPointFromAreaPoint\([^)]*\)\s*\{"
        )
        self.assertIsNotNone(body)
        self.assertIn("anchor.dx - point.dx", body)
        self.assertNotIn("unrelated", body)
        self.assertIsNone(
            module._extract_method_body(source, r"Offset\s+_absent\([^)]*\)\s*\{")
        )

    def test_real_repository_currently_satisfies_every_check(self) -> None:
        """合成树证明判据可判，真实仓库证明判据当下成立。"""

        module = _load_module()
        violations: list[str] = []
        for check in (
            module._check_forbidden_symbols,
            module._check_no_previous_front_baseline,
            module._check_no_retired_backward_leaf_renderer,
            module._check_host_library_parts,
            module._check_frame_builder_native_back,
            module._check_native_back_draw_soft_in_host_helpers,
            module._check_recto_verso_split_in_host,
            module._check_backward_texture_binding,
            module._check_soft_geometry_helper_clean,
            module._check_projected_frame_fields,
            module._check_backward_visual_replay_mapping,
        ):
            violations.extend(check())
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
