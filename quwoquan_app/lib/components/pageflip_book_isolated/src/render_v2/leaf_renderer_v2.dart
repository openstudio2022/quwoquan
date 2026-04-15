import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render_v2/leaf_mesh_builder_v2.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

class IsolatedLeafRendererV2 extends StatelessWidget {
  const IsolatedLeafRendererV2({
    super.key,
    required this.scene,
    this.lightingProgram,
    this.backfaceProgram,
  });

  final IsolatedLeafRenderSceneV2 scene;
  final ui.FragmentProgram? lightingProgram;
  final ui.FragmentProgram? backfaceProgram;

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(
        size: scene.stageSize,
        painter: _IsolatedLeafRendererPainter(
          scene: scene,
          lightingProgram: lightingProgram,
          backfaceProgram: backfaceProgram,
        ),
      ),
    );
  }
}

class _IsolatedLeafRendererPainter extends CustomPainter {
  const _IsolatedLeafRendererPainter({
    required this.scene,
    required this.lightingProgram,
    required this.backfaceProgram,
  });

  final IsolatedLeafRenderSceneV2 scene;
  final ui.FragmentProgram? lightingProgram;
  final ui.FragmentProgram? backfaceProgram;

  @override
  void paint(Canvas canvas, Size size) {
    if (scene.drawCoveredCurrentUnderlay) {
      _drawPageRect(canvas, scene.textures.verso.image);
    }
    _drawBottomPage(canvas);
    _drawBottomShadow(canvas);
    _drawBackSurface(canvas);
    _drawFrontSurface(canvas);
    _drawSpineAmbient(canvas);
  }

  void _drawPageRect(Canvas canvas, ui.Image image) {
    canvas.drawImageRect(
      image,
      Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      scene.pageRect,
      Paint()
        ..isAntiAlias = true
        ..filterQuality = FilterQuality.high,
    );
  }

  void _drawBottomPage(Canvas canvas) {
    canvas.save();
    canvas.clipPath(scene.meshFrame.bottomClipPath);
    _drawPageRect(canvas, scene.textures.bottom.image);
    canvas.restore();
  }

  void _drawBottomShadow(Canvas canvas) {
    final foldX =
        scene.pageRect.left +
        scene.pageRect.width * scene.meshFrame.foldXNormalized;
    final bandWidth = math.max(scene.pageRect.width * 0.14, 22.0).toDouble();
    final rect = Rect.fromLTRB(
      math.max(scene.pageRect.left, foldX - bandWidth),
      scene.pageRect.top,
      math.min(scene.pageRect.right, foldX + bandWidth),
      scene.pageRect.bottom,
    );
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }
    canvas.save();
    canvas.clipPath(scene.meshFrame.bottomClipPath);
    canvas.drawRect(
      rect,
      Paint()
        ..shader = ui.Gradient.linear(
          Offset(rect.left, rect.top),
          Offset(rect.right, rect.top),
          <Color>[
            scene.lightConfig.shadowColor.withValues(alpha: 0.18),
            scene.lightConfig.shadowColor.withValues(alpha: 0.06),
            AppColors.transparent,
          ],
          const <double>[0.0, 0.45, 1.0],
        ),
    );
    canvas.restore();
  }

  void _drawBackSurface(Canvas canvas) {
    final backSurface = scene.meshFrame.backSurface;
    if (backSurface == null) {
      return;
    }
    canvas.save();
    canvas.clipPath(scene.meshFrame.leafClipPath);
    _drawTexturedSurface(canvas, backSurface, scene.textures.verso.image);
    canvas.drawVertices(
      backSurface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..color = scene.lightConfig.paperTintColor.withValues(alpha: 0.08),
    );
    canvas.drawVertices(
      backSurface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..color = scene.lightConfig.shadowColor.withValues(alpha: 0.05),
    );
    canvas.restore();
  }

  void _drawFrontSurface(Canvas canvas) {
    canvas.save();
    canvas.clipPath(scene.meshFrame.leafClipPath);
    _drawTexturedSurface(
      canvas,
      scene.meshFrame.frontSurface,
      scene.textures.recto.image,
    );
    canvas.drawVertices(
      scene.meshFrame.frontSurface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..color = scene.lightConfig.highlightColor.withValues(alpha: 0.03),
    );
    canvas.restore();
  }

  void _drawTexturedSurface(
    Canvas canvas,
    LeafMeshSurfaceV2 surface,
    ui.Image image,
  ) {
    final imageShader = ui.ImageShader(
      image,
      ui.TileMode.clamp,
      ui.TileMode.clamp,
      Matrix4.diagonal3Values(
        image.width / scene.pageRect.width,
        image.height / scene.pageRect.height,
        1.0,
      ).storage,
    );
    canvas.drawVertices(
      surface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..filterQuality = FilterQuality.high
        ..shader = imageShader,
    );
  }

  void _drawSpineAmbient(Canvas canvas) {
    final spineRect = Rect.fromCenter(
      center: Offset(scene.pageRect.left, scene.pageRect.center.dy),
      width: scene.pageRect.width * 0.08,
      height: scene.pageRect.height + 20,
    );
    canvas.drawRect(
      spineRect,
      Paint()
        ..shader = ui.Gradient.linear(
          spineRect.centerLeft,
          spineRect.centerRight,
          <Color>[
            scene.lightConfig.shadowColor.withValues(alpha: 0.08),
            scene.lightConfig.ambientOcclusionColor.withValues(alpha: 0.05),
            AppColors.transparent,
          ],
          const <double>[0.0, 0.45, 1.0],
        ),
    );
  }

  @override
  bool shouldRepaint(covariant _IsolatedLeafRendererPainter oldDelegate) {
    return oldDelegate.scene != scene ||
        oldDelegate.lightingProgram != lightingProgram ||
        oldDelegate.backfaceProgram != backfaceProgram;
  }
}
