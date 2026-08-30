// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';

void main() {
  group('PublicContentLinkBuilder', () {
    test('只消费显式 publicWeb authority 并生成 canonical 路径', () {
      final links = PublicContentLinkBuilder(
        Uri.parse('https://public.example.test/'),
      );
      expect(
        links.entityHomepageWebUrl('hp_bipenggou'),
        'https://public.example.test/homepages/hp_bipenggou',
      );
    });

    test('缺失或非 HTTPS authority 失败关闭', () {
      expect(() => PublicContentLinkBuilder(Uri()), throwsArgumentError);
      expect(
        () => PublicContentLinkBuilder(Uri.parse('http://public.example.test')),
        throwsArgumentError,
      );
    });
  });
}
