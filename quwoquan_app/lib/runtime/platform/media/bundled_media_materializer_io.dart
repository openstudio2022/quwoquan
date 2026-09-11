import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_media_asset.dart';

/// 不进入网络下载缓存：按完整 bundle/content hash 物化不可变本地文件。
Future<String> materializeBundledVideo(BundledMediaAsset asset) async {
  if (asset.kind != 'video' || asset.mimeType != 'video/mp4') {
    throw const OfflineContentFailure('bundled_video_format_unsupported', unavailable: true);
  }
  final root = await getApplicationSupportDirectory();
  final directory = Directory('${root.path}/bundled_media/${asset.bundleDigest.substring(7)}');
  await directory.create(recursive: true);
  final file = File('${directory.path}/${asset.digest.substring(7)}.mp4');
  if (await file.exists()) {
    final digest = await sha256.bind(file.openRead()).first;
    if (await file.length() != asset.byteLength || 'sha256:$digest' != asset.digest) {
      throw const OfflineContentFailure('materialized_bundle_media_integrity_invalid');
    }
    return file.path;
  }
  final bytes = await asset.readVerifiedBytes();
  final attempt = await Directory.systemTemp.createTemp('bundled-video-');
  // 同一目标目录内 rename 原子发布；不覆盖其他 bundle 或网络缓存。
  final temporary = File('${directory.path}/${asset.digest.substring(7)}.${attempt.path.split('/').last}.tmp');
  try {
    await temporary.writeAsBytes(bytes, flush: true);
    await temporary.rename(file.path);
  } finally {
    if (await temporary.exists()) await temporary.delete();
    await attempt.delete();
  }
  return file.path;
}
