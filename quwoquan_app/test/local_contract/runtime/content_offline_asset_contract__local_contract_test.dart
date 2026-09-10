import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t2
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('真实包内内容通过制品 pin 和现役 Dart 生成 decoder', () async {
    final bytes = await rootBundle.load(offlineContentManifestAssetPath);
    final raw = bytes.buffer.asUint8List(
      bytes.offsetInBytes,
      bytes.lengthInBytes,
    );
    expect('sha256:${sha256.convert(raw)}', offlineContentManifestDigest);
    final manifest = jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
    expect(manifest['schema'], 'quwoquan.offline_content_bundle');
    final posts = manifest['posts'] as List<dynamic>;
    final ids = <String>{};
    for (final value in posts) {
      final row = value as Map<String, dynamic>;
      final projection = ContentPostProjection.fromWire(row['projection']);
      final detail = ContentPostDetailSlice.fromWire(row['detail']);
      final card = ContentPostViewData.fromWire(projection);
      final detailView = ContentPostDetailPayload.fromWire(detail);
      expect(card.id, detailView.post.id);
      expect(card.type, detailView.post.type);
      expect(ids.add(card.id), isTrue);
      if (card.type == 'article') {
        expect(detail.articleMarkdown, isNotEmpty);
      }
    }
    expect(ids, hasLength(3));
    for (final channel in manifest['channels'] as List<dynamic>) {
      final selected = (channel['orderedPostIds'] as List<dynamic>)
          .cast<String>();
      expect(selected.every(ids.contains), isTrue);
      if (channel['channelId'] == 'premium') expect(selected, hasLength(1));
    }
    ContentAppConfig.fromWire(manifest['configuration']['content']);
    for (final creator in manifest['creators'] as List<dynamic>) {
      PersonaProfileView.fromWire(creator['projection']);
    }
    for (final homepage in manifest['homepages'] as List<dynamic>) {
      HomepageIntroduction.fromWire(homepage['projection']);
    }
  });

  test('真实包内六个媒体均有完整字节，摘要及总量匹配', () async {
    final manifest = jsonDecode(
      await rootBundle.loadString(offlineContentManifestAssetPath),
    ) as Map<String, dynamic>;
    final media = manifest['media'] as List<dynamic>;
    var total = 0;
    for (final value in media) {
      final row = value as Map<String, dynamic>;
      final data = await rootBundle.load(row['assetPath'] as String);
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      expect(bytes.length, row['byteLength']);
      expect('sha256:${sha256.convert(bytes)}', row['sha256']);
      total += bytes.length;
    }
    expect(media, hasLength(6));
    expect(total, manifest['counts']['mediaBytes']);
    expect(total, 17177336);
  });
}
