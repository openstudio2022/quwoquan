import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';

/// 桌面本机图片的降采样缩略图 [ImageProvider]。
///
/// 设计（对齐业界 Glide/Coil/SDWebImage 的缩略图策略 + 跨平台防腐层）：
/// - 经 [FileStorageGateway] 读字节（不直接 `dart:io`），在**解码期**按 [targetPx] 降采样
///   （短边缩到 ~targetPx，保持比例，适配 `BoxFit.cover` 方格），避免把原图全分辨率位图
///   （一张 4000×3000 ≈ 40MB）灌进内存；
/// - 缓存键为 `(path, targetPx, scale)` 稳定值，解码后的小位图由 Flutter 全局 `imageCache`
///   （LRU，默认 100MiB）统一治理，**不再由页面长期持有原始字节**，从根上消除无界字节缓存；
/// - 解码失败经 `ImageStreamListener` 的 error 通道上报，由 `Image.errorBuilder` 降级占位。
@immutable
class DesktopThumbnailImage extends ImageProvider<DesktopThumbnailKey> {
  const DesktopThumbnailImage(
    this.path, {
    required this.gateway,
    required this.targetPx,
    this.scale = 1.0,
  });

  final String path;
  final FileStorageGateway gateway;

  /// 目标短边像素（= 显示边长 × devicePixelRatio）。原图短边 ≤ 此值则不放大。
  final int targetPx;
  final double scale;

  @override
  Future<DesktopThumbnailKey> obtainKey(ImageConfiguration configuration) {
    return SynchronousFuture<DesktopThumbnailKey>(
      DesktopThumbnailKey(path, targetPx, scale),
    );
  }

  @override
  ImageStreamCompleter loadImage(
    DesktopThumbnailKey key,
    ImageDecoderCallback decode,
  ) {
    return MultiFrameImageStreamCompleter(
      codec: _loadAsync(key, decode),
      scale: key.scale,
      debugLabel: path,
    );
  }

  Future<ui.Codec> _loadAsync(
    DesktopThumbnailKey key,
    ImageDecoderCallback decode,
  ) async {
    final raw = await gateway.readAsBytes(path);
    final bytes = raw is Uint8List ? raw : Uint8List.fromList(raw);
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    return decode(
      buffer,
      getTargetSize: (int intrinsicWidth, int intrinsicHeight) {
        final shorter = math.min(intrinsicWidth, intrinsicHeight);
        if (shorter <= key.targetPx || shorter <= 0) {
          return ui.TargetImageSize(
            width: intrinsicWidth,
            height: intrinsicHeight,
          );
        }
        final factor = key.targetPx / shorter;
        return ui.TargetImageSize(
          width: math.max(1, (intrinsicWidth * factor).round()),
          height: math.max(1, (intrinsicHeight * factor).round()),
        );
      },
    );
  }

  @override
  bool operator ==(Object other) {
    return other is DesktopThumbnailImage &&
        other.path == path &&
        other.targetPx == targetPx &&
        other.scale == scale &&
        identical(other.gateway, gateway);
  }

  @override
  int get hashCode => Object.hash(path, targetPx, scale, gateway);

  @override
  String toString() =>
      'DesktopThumbnailImage(path: $path, targetPx: $targetPx, scale: $scale)';
}

/// [DesktopThumbnailImage] 的缓存键：路径 + 目标像素 + scale 三者相同即视为同一图。
@immutable
class DesktopThumbnailKey {
  const DesktopThumbnailKey(this.path, this.targetPx, this.scale);

  final String path;
  final int targetPx;
  final double scale;

  @override
  bool operator ==(Object other) {
    return other is DesktopThumbnailKey &&
        other.path == path &&
        other.targetPx == targetPx &&
        other.scale == scale;
  }

  @override
  int get hashCode => Object.hash(path, targetPx, scale);
}
