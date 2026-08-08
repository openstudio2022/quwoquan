import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_creations_participant_slots.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleMembershipApprovalPageBuilder = Widget Function(String circleId);

typedef CircleObjectIntersectionBuilder =
    Widget Function({
      required Key key,
      required ObjectIntersectionQuery query,
      required String title,
      required bool isDark,
      required String emptyText,
      required Key emptyKey,
    });

typedef CircleObjectImpactBuilder =
    Widget Function({
      required String objectId,
      required ReferralSource referralSource,
      required String title,
      required String enumerableHint,
      required Key cardKey,
      required bool topDivider,
    });

typedef CircleMembersSectionBuilder =
    Widget Function({required String circleId, required bool isDark});

typedef CircleGroupMembershipPanelBuilder =
    Widget Function({
      required String circleId,
      required CircleGroupSlice group,
      required CircleGroupMembershipAccess access,
      required bool isDark,
    });

typedef CircleStorageSectionBuilder =
    Widget Function({
      required String circleId,
      required bool isDark,
      required int storageUsedBytes,
      required int storageQuotaBytes,
    });

typedef CircleCallStarter =
    Future<void> Function({
      required BuildContext context,
      required WidgetRef ref,
      required RtcCallEntryIntent intent,
      required AppUiSurface sourceSurface,
    });

/// Circle source owner 对参与对象 presentation 的完整 typed slots。
///
/// CircleShell 只拥有圈子页面的布局与交互状态；Membership、Group、File、
/// Recommendation 与 RTC 的具体 Widget/导航实现只在 runtime/di 组合根绑定。
final class CircleShellParticipantSlots {
  const CircleShellParticipantSlots({
    required this.buildMembershipApprovalPage,
    required this.buildObjectIntersection,
    required this.buildObjectImpact,
    required this.creations,
    required this.buildMembersSection,
    required this.buildGroupMembershipPanel,
    required this.buildStorageSection,
    required this.startCall,
  });

  final CircleMembershipApprovalPageBuilder buildMembershipApprovalPage;
  final CircleObjectIntersectionBuilder buildObjectIntersection;
  final CircleObjectImpactBuilder buildObjectImpact;
  final CircleCreationsParticipantSlots creations;
  final CircleMembersSectionBuilder buildMembersSection;
  final CircleGroupMembershipPanelBuilder buildGroupMembershipPanel;
  final CircleStorageSectionBuilder buildStorageSection;
  final CircleCallStarter startCall;
}
