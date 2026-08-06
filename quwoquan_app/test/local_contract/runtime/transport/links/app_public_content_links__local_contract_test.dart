// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';

void main() {
  group('AppPublicContentLinks', () {
    test('只消费 package-bound publicWeb authority，缺失时保持相对路径', () {
      final base = CloudRuntimeConfig.publicWebBaseUrl.trim().replaceAll(
        RegExp(r'/+$'),
        '',
      );
      expect(
        AppPublicContentLinks.entityHomepageWebUrl('hp_bipenggou'),
        '$base/homepages/hp_bipenggou',
      );
    });
  });
}
