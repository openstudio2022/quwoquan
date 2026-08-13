import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_impact_provider.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/author_impact_query.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/entity_impact_provider.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_recommendation_slots.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/author_impact_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_reason_chip.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_entry_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/creator_flywheel_proof_row.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_experience_asset_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_impact_preview_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_section.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/other_profile_intersection_card.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_recommendation_slots.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Widget? _buildIntersectionReason(
  List<IntersectionReason>? reasons, {
  required bool isDark,
  required ReferralSource referralSource,
  required String contextObjectName,
  required IntersectionTarget contextObjectTarget,
}) => IntersectionReasonChip.fromReasons(
  reasons,
  isDark: isDark,
  referralSource: referralSource,
  contextObjectName: contextObjectName,
  contextObjectTarget: contextObjectTarget,
);

Widget _buildHomepageObjectIntersection({
  required Key key,
  required ObjectIntersectionQuery query,
  required String title,
  required bool isDark,
  required String emptyText,
  required Key emptyKey,
}) => ObjectIntersectionSection(
  key: key,
  query: query,
  title: title,
  isDark: isDark,
  emptyText: emptyText,
  emptyKey: emptyKey,
);

Widget _buildHomepageObjectImpact({
  required String objectId,
  required ReferralSource referralSource,
  required String title,
  required String enumerableHint,
  required Key cardKey,
  required bool topDivider,
}) {
  final id = objectId.trim();
  if (id.isEmpty) {
    return const SizedBox.shrink();
  }
  return Consumer(
    builder: (context, ref, _) => ref
        .watch(entityImpactProvider(id))
        .when(
          loading: () => const SizedBox.shrink(),
          error: (_, _) => const SizedBox.shrink(),
          data: (summary) => ObjectImpactPreviewCard.entity(
            summary: summary,
            contentBehaviorTracker: ref.watch(contentBehaviorTrackerProvider),
            referralSource: referralSource,
            title: title,
            enumerableHint: enumerableHint,
            cardKey: cardKey,
            topDivider: topDivider,
          ),
        ),
  );
}

Widget _buildOtherProfileIntersection({required String userId}) =>
    OtherProfileIntersectionCard(userId: userId);

Widget _buildMyProfileIntersection({required bool isDark}) =>
    MyIntersectionInboxCard(isDark: isDark);

Widget _buildMyProfileGatherings({required bool isDark}) =>
    MyGatheringsEntryCard(isDark: isDark);

Widget _buildMyProfileExperience({required bool isDark}) =>
    MyExperienceAssetCard(isDark: isDark);

Widget _buildMyProfileCreatorProof({required String personaId}) =>
    CreatorFlywheelProofRow(personaId: personaId);

Widget _buildAuthorImpact({
  required AuthorImpactSummary summary,
  required bool isDark,
  required bool isMine,
  required AuthorImpactQuery authorImpactQuery,
  required ContentBehaviorTrackerPort contentBehaviorTracker,
}) => AuthorImpactCard(
  summary: summary,
  isDark: isDark,
  isMine: isMine,
  authorImpactQuery: authorImpactQuery,
  contentBehaviorTracker: contentBehaviorTracker,
);

/// Entity homepage source owner 的 production Recommendation participant 绑定。
const HomepageRecommendationSlots homepageRecommendationSlots =
    HomepageRecommendationSlots(
      buildIntersectionReason: _buildIntersectionReason,
      buildObjectIntersection: _buildHomepageObjectIntersection,
      buildObjectImpact: _buildHomepageObjectImpact,
    );

/// Persona source owner 的 production participant 绑定（Recommendation + Circle）。
const ProfileRecommendationSlots profileRecommendationSlots =
    ProfileRecommendationSlots(
      buildOtherIntersection: _buildOtherProfileIntersection,
      buildMyIntersection: _buildMyProfileIntersection,
      buildAuthorImpact: _buildAuthorImpact,
      buildIntersectionReason: _buildIntersectionReason,
      buildMyGatherings: _buildMyProfileGatherings,
      buildMyExperience: _buildMyProfileExperience,
      buildCreatorProof: _buildMyProfileCreatorProof,
    );

/// CircleShell 仍在 runtime/di 组合期使用的同一 typed slot。
Widget buildCircleObjectImpactSlot({
  required String objectId,
  required ReferralSource referralSource,
  required String title,
  required String enumerableHint,
  required Key cardKey,
  required bool topDivider,
}) {
  final id = objectId.trim();
  if (id.isEmpty) {
    return const SizedBox.shrink();
  }
  return Consumer(
    builder: (context, ref, _) => ref
        .watch(circleImpactProvider(id))
        .when(
          loading: () => const SizedBox.shrink(),
          error: (_, _) => const SizedBox.shrink(),
          data: (summary) => ObjectImpactPreviewCard.circle(
            summary: summary,
            contentBehaviorTracker: ref.watch(contentBehaviorTrackerProvider),
            referralSource: referralSource,
            title: title,
            enumerableHint: enumerableHint,
            cardKey: cardKey,
            topDivider: topDivider,
          ),
        ),
  );
}
