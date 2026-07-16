import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('alpha fixture bundle is immutable and content addressed', () {
    expect(alphaFixtureBundle.assets, isNotEmpty);

    for (final entry in alphaFixtureBundle.assets.entries) {
      final asset = entry.value;
      expect(asset.domain, entry.key);
      expect(asset.refs, isNotEmpty);
      expect(jsonDecode(asset.sourceJson), isA<Object>());
      expect(
        sha256.convert(utf8.encode(asset.sourceJson)).toString(),
        asset.sourceSha256,
      );
    }
  });
}
