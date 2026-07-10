import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';

void main() {
  group('AppPublicContentLinks', () {
    test('builds entity homepage public URL from link template', () {
      expect(
        AppPublicContentLinks.entityHomepageWebUrl('hp_bipenggou'),
        'https://alpha-api.quwoquan-env.test:17000/homepages/hp_bipenggou',
      );
    });
  });
}
