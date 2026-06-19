import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';

void main() {
  group('AppPublicContentLinks', () {
    test('builds entity homepage public URL from link template', () {
      expect(
        AppPublicContentLinks.entityHomepageWebUrl('hp_bipenggou'),
        'https://127.0.0.1:17000/homepages/hp_bipenggou',
      );
    });
  });
}
