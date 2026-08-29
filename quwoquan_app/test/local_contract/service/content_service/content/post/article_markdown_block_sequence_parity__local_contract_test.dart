// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-006
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-003
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';

void main() {
  test('Dart article codec matches shared semantic block sequence', () {
    final contract = _loadContract();
    final cases = (contract['cases'] as List<Object?>)
        .cast<Map<String, Object?>>();

    for (final fixtureCase in cases) {
      final document = ArticleMarkdownCodec.parseDocument(
        fixtureCase['markdown']! as String,
        assetManifest: <String, Object?>{
          'assets': fixtureCase['assets']! as List<Object?>,
        },
        assetManifestResolver: const MediaAssetManifestResolver(
          resolveReference: _resolveFixtureReference,
          imageCdnBaseUrl: 'https://cdn.example.test',
        ),
      );
      final observed = document.nodes
          .where((node) => !node.isDocumentTitle)
          .map(
            (node) => <String, String>{
              'type': switch (node.type.name) {
                'headingMajor' => 'heading2',
                'headingMinor' => 'heading3',
                'figure' => 'image',
                'divider' => 'divider',
                final type => type,
              },
              'assetId': node.assetId,
            },
          )
          .toList(growable: false);
      final expected = (fixtureCase['expectedSequence']! as List<Object?>)
          .map(
            (entry) =>
                Map<String, String>.from(entry! as Map<Object?, Object?>),
          )
          .toList(growable: false);

      expect(observed, expected, reason: fixtureCase['name']! as String);
      expect(
        document.assets
            .map(
              (asset) => <String, String>{
                'assetId': asset.id,
                'cdnUrl': asset.imageUrl,
              },
            )
            .toList(growable: false),
        (fixtureCase['assets']! as List<Object?>)
            .map((entry) => Map<String, Object?>.from(entry! as Map))
            .map(
              (entry) => <String, String>{
                'assetId': entry['assetId']! as String,
                'cdnUrl': entry['cdnUrl']! as String,
              },
            )
            .toList(growable: false),
        reason: '${fixtureCase['name']} image delivery projection',
      );
      expect(
        _fingerprint(observed),
        fixtureCase['expectedFingerprint'],
        reason: fixtureCase['name']! as String,
      );
    }
  });
}

Map<String, Object?> _loadContract() {
  final direct = File(
    '../quwoquan_service/services/content-service/contracts/content/post/markdown_block_sequence_cases.json',
  );
  final file = direct.existsSync()
      ? direct
      : File(
          'quwoquan_service/services/content-service/contracts/content/post/markdown_block_sequence_cases.json',
        );
  return jsonDecode(file.readAsStringSync()) as Map<String, Object?>;
}

String _fingerprint(List<Map<String, String>> sequence) {
  final canonical = sequence
      .map((entry) => '${entry['type']}|${entry['assetId']}')
      .join('\n');
  return sha256.convert(utf8.encode(canonical)).toString();
}

String _resolveFixtureReference(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) => raw;
