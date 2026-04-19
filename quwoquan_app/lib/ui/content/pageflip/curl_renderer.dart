import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticlePageCurlRenderConfig {
  const ArticlePageCurlRenderConfig({
    this.enableBackPaperWash = true,
    this.enableBackCreaseOcclusion = true,
    this.enableBottomProjection = true,
    this.enableSpineAmbient = true,
  });

  final bool enableBackPaperWash;
  final bool enableBackCreaseOcclusion;
  final bool enableBottomProjection;
  final bool enableSpineAmbient;
}

@immutable
class ArticlePageCurlRenderScene {
  const ArticlePageCurlRenderScene({
    required this.stageSize,
    required this.pageRect,
    required this.textures,
    required this.meshFrame,
    required this.lightConfig,
    required this.lightState,
    required this.direction,
    required this.corner,
    this.renderConfig = const ArticlePageCurlRenderConfig(),
  });

  final Size stageSize;
  final Rect pageRect;
  final ArticlePageTextureBundle textures;
  final ArticlePageCurlFrame meshFrame;
  final ArticlePageCurlLightConfig lightConfig;
  final ArticlePageCurlLightState lightState;
  final StPageFlipDirection direction;
  final StPageFlipCorner corner;
  final ArticlePageCurlRenderConfig renderConfig;
}

Rect resolveArticlePageBottomProjectionBand(
  Rect pageRect,
  double foldXNormalized,
) {
  final foldX = pageRect.left + pageRect.width * foldXNormalized;
  final halfWidth = math.max(pageRect.width * 0.16, 24.0).toDouble();
  final left = math.max(pageRect.left, foldX - halfWidth).toDouble();
  final right = math.min(pageRect.right, foldX).toDouble();
  return Rect.fromLTRB(left, pageRect.top, right, pageRect.bottom);
}

class ArticlePageCurlRenderer extends StatelessWidget {
  const ArticlePageCurlRenderer({
    super.key,
    required this.scene,
    this.lightingProgram,
    this.backfaceProgram,
  });

  final ArticlePageCurlRenderScene scene;
  final ui.FragmentProgram? lightingProgram;
  final ui.FragmentProgram? backfaceProgram;

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(
        size: scene.stageSize,
        painter: _ArticlePageCurlRendererPainter(
          scene: scene,
          lightingProgram: lightingProgram,
          backfaceProgram: backfaceProgram,
        ),
      ),
    );
  }
}

class _ArticlePageCurlRendererPainter extends CustomPainter {
  const _ArticlePageCurlRendererPainter({
    required this.scene,
    required this.lightingProgram,
    required this.backfaceProgram,
  });

  final ArticlePageCurlRenderScene scene;
  final ui.FragmentProgram? lightingProgram;
  final ui.FragmentProgram? backfaceProgram;

  @override
  void paint(Canvas canvas, Size size) {
    _drawBottomPage(canvas);
    if (scene.renderConfig.enableBottomProjection) {
      _drawBottomProjection(canvas);
    }
    _drawFrontSurface(canvas);
    _drawBackSurface(canvas);
    if (scene.renderConfig.enableSpineAmbient) {
      _drawSpineAmbient(canvas);
    }
  }

  void _drawBottomPage(Canvas canvas) {
    canvas.save();
    canvas.clipPath(scene.meshFrame.bottomClipPath);
    final image = scene.textures.bottom.image;
    canvas.drawImageRect(
      image,
      Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      scene.pageRect,
      Paint()
        ..isAntiAlias = true
        ..filterQuality = FilterQuality.high,
    );
    canvas.restore();
  }

  void _drawBottomProjection(Canvas canvas) {
    if (lightingProgram == null) {
      return;
    }
    canvas.save();
    canvas.clipPath(scene.meshFrame.bottomClipPath);
    final projectionBand = _bottomProjectionBand();
    if (projectionBand.width <= 0 || projectionBand.height <= 0) {
      canvas.restore();
      return;
    }
    canvas.clipRect(projectionBand);
    final shader = lightingProgram!.fragmentShader();
    _setLightingUniforms(
      shader,
      progress: scene.meshFrame.progress,
      direction: scene.direction,
      foldXNormalized: scene.meshFrame.foldXNormalized,
      curlLift: scene.lightState.curlLift,
      tunnelShadowStrength: scene.lightState.tunnelShadowStrength,
      edgeHighlightStrength: 0,
      shadowStrength: scene.lightState.bottomShadowStrength,
      shadowColor: scene.lightConfig.shadowColor,
      highlightColor: Color.fromARGB(0, 0, 0, 0),
      ambientColor: scene.lightConfig.ambientOcclusionColor.withValues(
        alpha: 0.14,
      ),
    );
    canvas.drawRect(
      scene.pageRect,
      Paint()
        ..isAntiAlias = true
        ..shader = shader,
    );
    canvas.restore();
  }

  Rect _bottomProjectionBand() {
    return resolveArticlePageBottomProjectionBand(
      scene.pageRect,
      scene.meshFrame.foldXNormalized,
    );
  }

  void _drawBackSurface(Canvas canvas) {
    final backSurface = scene.meshFrame.backSurface;
    if (backSurface == null) {
      return;
    }
    _drawBackAlbedo(canvas, backSurface);
    if (scene.renderConfig.enableBackPaperWash) {
      _drawBackPaperWash(canvas, backSurface);
    }
    if (scene.renderConfig.enableBackCreaseOcclusion) {
      _drawBackCreaseOcclusion(canvas, backSurface);
    }
  }

  void _drawBackAlbedo(Canvas canvas, ArticlePageCurlMeshSurface backSurface) {
    _drawTexturedSurface(
      canvas,
      backSurface,
      scene.textures.verso,
      blendMode: BlendMode.src,
    );
  }

  void _drawBackPaperWash(
    Canvas canvas,
    ArticlePageCurlMeshSurface backSurface,
  ) {
    final paperWashAlpha =
        0.012 + scene.lightState.backfaceTintStrength * 0.018;
    canvas.drawVertices(
      backSurface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..color = scene.lightConfig.paperTintColor.withValues(
          alpha: paperWashAlpha,
        ),
    );
  }

  void _drawBackCreaseOcclusion(
    Canvas canvas,
    ArticlePageCurlMeshSurface backSurface,
  ) {
    if (backfaceProgram == null) {
      return;
    }
    final shader = backfaceProgram!.fragmentShader();
    _setBackfaceUniforms(
      shader,
      progress: scene.meshFrame.progress,
      direction: scene.direction,
      foldXNormalized: scene.meshFrame.foldXNormalized,
      tintStrength: scene.lightState.backfaceTintStrength,
      occlusionStrength: scene.lightState.backfaceOcclusionStrength,
      paperTintColor: scene.lightConfig.paperTintColor,
      occlusionColor: scene.lightConfig.shadowColor,
    );
    canvas.drawVertices(
      backSurface.vertices,
      BlendMode.srcOver,
      Paint()
        ..isAntiAlias = true
        ..shader = shader,
    );
  }

  void _drawFrontSurface(Canvas canvas) {
    final frontSurface = scene.meshFrame.frontSurface;
    if (frontSurface == null) {
      return;
    }
    _drawTexturedSurface(
      canvas,
      frontSurface,
      scene.textures.recto,
      blendMode: BlendMode.src,
    );
    if (lightingProgram != null) {
      final shader = lightingProgram!.fragmentShader();
      _setLightingUniforms(
        shader,
        progress: scene.meshFrame.progress,
        direction: scene.direction,
        foldXNormalized: scene.meshFrame.foldXNormalized,
        curlLift: scene.lightState.curlLift,
        tunnelShadowStrength: scene.lightState.tunnelShadowStrength,
        edgeHighlightStrength: scene.lightState.edgeHighlightStrength,
        shadowStrength: scene.lightState.spineAmbientStrength,
        shadowColor: scene.lightConfig.shadowColor,
        highlightColor: scene.lightConfig.highlightColor,
        ambientColor: scene.lightConfig.ambientOcclusionColor,
      );
      canvas.drawVertices(
        frontSurface.vertices,
        BlendMode.srcOver,
        Paint()
          ..isAntiAlias = true
          ..shader = shader,
      );
    }
  }

  void _drawTexturedSurface(
    Canvas canvas,
    ArticlePageCurlMeshSurface surface,
    ArticlePageTextureSnapshot snapshot, {
    BlendMode blendMode = BlendMode.src,
  }) {
    final imageShader = ui.ImageShader(
      snapshot.image,
      ui.TileMode.clamp,
      ui.TileMode.clamp,
      Matrix4.diagonal3Values(
        snapshot.pixelWidthPerLogical,
        snapshot.pixelHeightPerLogical,
        1.0,
      ).storage,
    );
    canvas.drawVertices(
      surface.vertices,
      blendMode,
      Paint()
        ..isAntiAlias = false
        ..filterQuality = FilterQuality.none
        ..shader = imageShader,
    );
  }

  void _drawSpineAmbient(Canvas canvas) {
    final spineRect = Rect.fromCenter(
      center: Offset(scene.pageRect.left, scene.pageRect.center.dy),
      width: scene.pageRect.width * 0.08,
      height: scene.pageRect.height + 24,
    );
    canvas.drawRect(
      spineRect,
      Paint()
        ..shader = ui.Gradient.linear(
          spineRect.centerLeft,
          spineRect.centerRight,
          <Color>[
            scene.lightConfig.shadowColor.withValues(
              alpha: 0.08 + scene.lightState.spineAmbientStrength * 0.12,
            ),
            scene.lightConfig.ambientOcclusionColor.withValues(
              alpha: 0.03 + scene.lightState.spineAmbientStrength * 0.08,
            ),
            Color.fromARGB(0, 0, 0, 0),
          ],
          const <double>[0.0, 0.42, 1.0],
        ),
    );
  }

  void _setLightingUniforms(
    ui.FragmentShader shader, {
    required double progress,
    required StPageFlipDirection direction,
    required double foldXNormalized,
    required double curlLift,
    required double tunnelShadowStrength,
    required double edgeHighlightStrength,
    required double shadowStrength,
    required Color shadowColor,
    required Color highlightColor,
    required Color ambientColor,
  }) {
    shader
      ..setFloat(0, scene.stageSize.width)
      ..setFloat(1, scene.stageSize.height)
      ..setFloat(2, progress)
      ..setFloat(3, direction == StPageFlipDirection.forward ? 1.0 : 0.0)
      ..setFloat(4, foldXNormalized)
      ..setFloat(5, curlLift)
      ..setFloat(6, tunnelShadowStrength)
      ..setFloat(7, edgeHighlightStrength)
      ..setFloat(8, shadowStrength);
    _setColor(shader, 9, shadowColor);
    _setColor(shader, 13, highlightColor);
    _setColor(shader, 17, ambientColor);
    _setRect(shader, 21, scene.pageRect);
  }

  void _setBackfaceUniforms(
    ui.FragmentShader shader, {
    required double progress,
    required StPageFlipDirection direction,
    required double foldXNormalized,
    required double tintStrength,
    required double occlusionStrength,
    required Color paperTintColor,
    required Color occlusionColor,
  }) {
    shader
      ..setFloat(0, scene.stageSize.width)
      ..setFloat(1, scene.stageSize.height)
      ..setFloat(2, progress)
      ..setFloat(3, direction == StPageFlipDirection.forward ? 1.0 : 0.0)
      ..setFloat(4, foldXNormalized)
      ..setFloat(5, tintStrength)
      ..setFloat(6, occlusionStrength);
    _setColor(shader, 7, paperTintColor);
    _setColor(shader, 11, occlusionColor);
    _setRect(shader, 15, scene.pageRect);
  }

  void _setColor(ui.FragmentShader shader, int startIndex, Color color) {
    shader
      ..setFloat(startIndex, color.r)
      ..setFloat(startIndex + 1, color.g)
      ..setFloat(startIndex + 2, color.b)
      ..setFloat(startIndex + 3, color.a);
  }

  void _setRect(ui.FragmentShader shader, int startIndex, Rect rect) {
    shader
      ..setFloat(startIndex, rect.left)
      ..setFloat(startIndex + 1, rect.top)
      ..setFloat(startIndex + 2, rect.width)
      ..setFloat(startIndex + 3, rect.height);
  }

  @override
  bool shouldRepaint(covariant _ArticlePageCurlRendererPainter oldDelegate) {
    return oldDelegate.scene != scene ||
        oldDelegate.lightingProgram != lightingProgram ||
        oldDelegate.backfaceProgram != backfaceProgram;
  }
}
