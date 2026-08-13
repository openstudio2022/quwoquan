import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ObjectHomepageText;
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_kind_mapping.dart'
    show intersectionMutualCountOf;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show FollowSubjectKind, IntersectionReason;

/// 内容表面共用的「想去」动作闭环（意图环 Aha 1）：
/// 登录门（双目标续接）→ wishlist 行为事实上报 → 诚实两态反馈
/// （有对象交集点名共同人数，无交集只确认动作，不伪造）。
///
/// 该 helper 是无状态动作，不维护想去状态副本；状态展示由各表面按需读
/// `GetEntityWishlistState`（服务端真相）或保持纯动作入口。
Future<void> runEntityWishlistAddAction(
  BuildContext context,
  WidgetRef ref, {
  required String homepageId,
  String displayName = '',
  required String sourceSurfaceId,
  required String continuationOwnerToken,
  String? feedRequestId,
  ReferralSource? referralSource,
}) async {
  final normalizedHomepageId = homepageId.trim();
  if (normalizedHomepageId.isEmpty) {
    return;
  }
  if (!ref.read(authSessionControllerProvider).isAuthenticated) {
    // 双目标契约：关闭登录回安全态（首页），登录成功经续接完成想去。
    ref
        .read(authContinuationProvider.notifier)
        .set(
          WishlistHomepageContinuation(homepageId: normalizedHomepageId),
          ownerToken: continuationOwnerToken,
        );
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.wishlist,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
    return;
  }
  final tracker = ref.read(contentBehaviorTrackerProvider);
  tracker.trackWishlistAdd(
    normalizedHomepageId,
    objectKind: FollowSubjectKind.homepage.wireName,
    displayName: displayName.trim().isEmpty ? null : displayName.trim(),
    sourceSurface: sourceSurfaceId,
    feedRequestId: feedRequestId,
    referralSource: referralSource,
  );
  await tracker.flush();
  if (!context.mounted) {
    return;
  }
  await showEntityWishlistIntersectionFeedback(
    context,
    ref,
    homepageId: normalizedHomepageId,
    telemetrySource: 'content.entity_wishlist_action.intersection_feedback',
  );
}

/// Aha 时刻（诚实两态）：想去成功后立刻回答「谁也想去」。
/// 交集读取失败按未附着降级（只确认动作），不阻断主动作、不伪造共同人数。
Future<void> showEntityWishlistIntersectionFeedback(
  BuildContext context,
  WidgetRef ref, {
  required String homepageId,
  required String telemetrySource,
}) async {
  final personaId = ref
      .read(authSessionControllerProvider)
      .activePersonaId
      .trim();
  List<IntersectionReason> reasons = const <IntersectionReason>[];
  try {
    reasons = await ref.read(
      objectSharedReasonsProvider(
        ObjectIntersectionQuery(
          objectAId: personaId,
          objectAType: 'person',
          objectBId: homepageId,
          objectBType: 'homepage',
        ),
      ).future,
    );
  } catch (error, stackTrace) {
    unawaited(
      ref
          .read(exceptionTelemetryPortProvider)
          .recordHandledException(
            source: telemetrySource,
            error: error,
            stackTrace: stackTrace,
          ),
    );
  }
  if (!context.mounted) {
    return;
  }
  final wishReason = reasons.isEmpty
      ? null
      : reasons.firstWhere(
          (reason) => reason.kind == 'coWishlistedEntity',
          orElse: () => reasons.first,
        );
  final mutualCount = wishReason == null
      ? 0
      : intersectionMutualCountOf(wishReason);
  if (wishReason == null || mutualCount <= 0) {
    AppToast.show(context, ObjectHomepageText.wishlistAddedFeedback);
    return;
  }
  AppToast.show(
    context,
    ObjectHomepageText.wishlistSharedFeedback(mutualCount),
    actionLabel: ObjectHomepageText.wishlistSharedFeedbackViewAction,
    onAction: () {
      if (!context.mounted) return;
      context.push(AppRoutePaths.homepageDetail(id: homepageId));
    },
  );
}
