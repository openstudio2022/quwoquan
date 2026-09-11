import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';

/// Flutter 解码前完成完整闭包与当前媒体字节校验；缓存 key 绑定快照摘要。
final class BundledImageProvider extends ImageProvider<BundledImageProvider> {
  const BundledImageProvider({
    required this.reference,
    required this.digest,
    required this.loadBundle,
  });
  final String reference;
  final String digest;
  final Future<OfflineContentBundle> Function() loadBundle;

  @override
  Future<BundledImageProvider> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(
    BundledImageProvider key,
    ImageDecoderCallback decode,
  ) => MultiFrameImageStreamCompleter(codec: _decode(decode), scale: 1);

  Future<ui.Codec> _decode(ImageDecoderCallback decode) async {
    final bundle = await loadBundle();
    final asset = bundle.media.lookup(reference);
    if (bundle.digest != digest || asset == null || asset.kind == 'video') {
      throw const OfflineContentFailure('bundle_image_reference_invalid');
    }
    return decode(
      await ui.ImmutableBuffer.fromUint8List(await asset.readVerifiedBytes()),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is BundledImageProvider &&
      other.reference == reference &&
      other.digest == digest;
  @override
  int get hashCode => Object.hash(reference, digest);
}
