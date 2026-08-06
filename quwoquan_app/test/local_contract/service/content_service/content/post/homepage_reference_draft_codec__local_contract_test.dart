import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';

// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/spec.md#sit-001

void main() {
  group('PublishSettings homepage local draft codec', () {
    test('round-trip preserves App ViewData without a Cloud Map decoder', () {
      const settings = PublishSettings(
        homepage: HomepageCanonicalReference(
          id: 'homepage-west-lake',
          homepageType: 'sight',
          title: '西湖景区',
          subtitle: '杭州',
          coverUrl: 'https://example.com/west-lake.jpg',
          status: 'published',
          canonicalEntityId: 'entity-west-lake',
        ),
      );

      final restored = PublishSettings.fromMap(settings.toMap());

      expect(restored.homepage?.id, 'homepage-west-lake');
      expect(restored.homepage?.homepageType, 'sight');
      expect(restored.homepage?.title, '西湖景区');
      expect(restored.homepage?.canonicalEntityId, 'entity-west-lake');
    });

    test('incomplete local draft reference fails closed', () {
      final restored = PublishSettings.fromMap(<String, Object?>{
        'homepage': <String, Object?>{
          'id': 'homepage-west-lake',
          'homepageType': 'sight',
        },
      });

      expect(restored.homepage, isNull);
    });

    test(
      'retired Cloud homepageId key is not accepted by local draft codec',
      () {
        final restored = PublishSettings.fromMap(<String, Object?>{
          'homepage': <String, Object?>{
            'homepageId': 'homepage-west-lake',
            'homepageType': 'sight',
            'title': '西湖景区',
          },
        });

        expect(restored.homepage, isNull);
      },
    );
  });
}
