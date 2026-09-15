import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';

/// Flutter 解码前完成完整闭包与当前媒体字节校验；缓存 key 绑定快照摘要。
final class BundledImageProvider extends ImageProvider<BundledImageProvider> {
  const BundledImageProvider({
    required this.reference,
    required this.digest,
    required this.loadBundle,
    this.sourceIdentity,
    this.checkScope,
  });
  final String reference;
  final String digest;
  final Future<OfflineContentBundle> Function() loadBundle;
  final Object? sourceIdentity;
  final void Function()? checkScope;
  Object get _identity => sourceIdentity ?? loadBundle;

  Future<void> _verifySourceBytes() async {
    checkScope?.call();
    final bundle = await loadBundle();
    checkScope?.call();
    final asset = bundle.media.lookup(reference);
    if (bundle.digest != digest || asset == null || asset.kind == 'video') {
      throw const OfflineContentFailure('bundle_image_reference_invalid');
    }
    await asset.readVerifiedBytes();
    checkScope?.call();
  }

  @override
  Future<BundledImageProvider> obtainKey(
    ImageConfiguration configuration,
  ) async {
    // ImageCache命中前仍核验实际字节；解码结果可复用但不可跨来源绕过完整性。
    await _verifySourceBytes();
    return this;
  }

  @override
  void resolveStreamForKey(
    ImageConfiguration configuration,
    ImageStream stream,
    BundledImageProvider key,
    ImageErrorListener handleError,
  ) {
    checkScope?.call();
    super.resolveStreamForKey(configuration, stream, key, handleError);
  }

  @override
  ImageStreamCompleter loadImage(
    BundledImageProvider key,
    ImageDecoderCallback decode,
  ) {
    checkScope?.call();
    return MultiFrameImageStreamCompleter(codec: _decode(decode), scale: 1);
  }

  Future<ui.Codec> _decode(ImageDecoderCallback decode) async {
    checkScope?.call();
    final bundle = await loadBundle();
    checkScope?.call();
    final asset = bundle.media.lookup(reference);
    if (bundle.digest != digest || asset == null || asset.kind == 'video') {
      throw const OfflineContentFailure('bundle_image_reference_invalid');
    }
    final bytes = await asset.readVerifiedBytes();
    checkScope?.call();
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    try {
      checkScope?.call();
    } catch (_) {
      buffer.dispose();
      rethrow;
    }
    final codec = await decode(buffer);
    try {
      checkScope?.call();
    } catch (_) {
      codec.dispose();
      rethrow;
    }
    return checkScope == null ? codec : _ScopeCheckedCodec(codec, checkScope!);
  }

  @override
  bool operator ==(Object other) =>
      other is BundledImageProvider &&
      other.reference == reference &&
      other.digest == digest &&
      identical(other._identity, _identity);
  @override
  int get hashCode =>
      Object.hash(reference, digest, identityHashCode(_identity));
}

/// 每帧发布前检查代际；解码途中失效时释放迟到帧与codec。
final class _ScopeCheckedCodec implements ui.Codec {
  _ScopeCheckedCodec(this.delegate, this.check);
  final ui.Codec delegate;
  final void Function() check;
  bool disposed = false;
  @override
  int get frameCount => delegate.frameCount;
  @override
  int get repetitionCount => delegate.repetitionCount;
  @override
  Future<ui.FrameInfo> getNextFrame() async {
    try {
      check();
    } catch (_) {
      dispose();
      rethrow;
    }
    final frame = await delegate.getNextFrame();
    try {
      check();
    } catch (_) {
      frame.image.dispose();
      dispose();
      rethrow;
    }
    return frame;
  }

  @override
  void dispose() {
    if (disposed) return;
    disposed = true;
    delegate.dispose();
  }
}
