// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-007.t2
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_recommendation_slots.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_section.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/other_profile_intersection_card.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_recommendation_slots.dart';

void main() {
  test('production composition binds source-owner typed slots', () {
    final HomepageRecommendationSlots homepageSlots =
        homepageRecommendationSlots;
    final ProfileRecommendationSlots profileSlots = profileRecommendationSlots;

    final otherProfile = profileSlots.buildOtherIntersection(userId: 'user-1');
    expect(otherProfile, isA<OtherProfileIntersectionCard>());

    final objectIntersection = homepageSlots.buildObjectIntersection(
      key: const ValueKey<String>('homepage-intersection-contract'),
      query: const ObjectIntersectionQuery(
        objectAId: 'viewer-1',
        objectAType: 'user',
        objectBId: 'homepage-1',
        objectBType: 'school',
      ),
      title: 'title-from-source-owner',
      isDark: false,
      emptyText: 'empty-from-source-owner',
      emptyKey: const ValueKey<String>('homepage-intersection-empty-contract'),
    );
    expect(objectIntersection, isA<ObjectIntersectionSection>());
  });

  test('source owners do not import Recommendation private presentation', () {
    const sources = <String>[
      'lib/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_shell.dart',
      'lib/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_shell_builders.dart',
      'lib/service/user_service/persona_management/persona/presentation/profile_shell.dart',
      'lib/service/user_service/persona_management/persona/presentation/profile_shell_builders.dart',
      'lib/service/user_service/persona_management/persona/presentation/profile_shell_builders_parts.dart',
      'lib/service/user_service/persona_management/persona/presentation/profile_works_tab.dart',
    ];
    const privatePrefix =
        'service/recommendation_service/recommendation/'
        'recommendation_feature_profile_view/presentation/';

    for (final source in sources) {
      final text = File(source).readAsStringSync();
      expect(text, isNot(contains(privatePrefix)), reason: source);
    }
  });

  test(
    'Recommendation impact widget consumes no source-owner private provider',
    () {
      final text = File(
        'lib/service/recommendation_service/recommendation/'
        'recommendation_feature_profile_view/presentation/'
        'object_impact_preview_card.dart',
      ).readAsStringSync();

      expect(text, isNot(contains('circle_impact_provider.dart')));
      expect(text, isNot(contains('entity_impact_provider.dart')));
    },
  );
}
