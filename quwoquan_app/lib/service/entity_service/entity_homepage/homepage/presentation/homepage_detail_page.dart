import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/generated/homepage_ui_config.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';
import 'package:quwoquan_app/runtime/di/runtime_package_dependencies.dart'
    show publicContentLinkBuilderProvider;
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/homepage_circle_presentation_slots.dart'
    show buildHomepageRecentGatheringsSlot;
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart'
    show objectSharedReasonsProvider;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_kind_mapping.dart'
    show intersectionMutualCountOf;
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/runtime/di/navigation/create_entry_navigation_arguments.dart';
import 'package:quwoquan_app/runtime/observability/trackers/homepage_product_action_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/domain/homepage_tab.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_shell.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider, journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageQueryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailEntityWishlistStateReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show homepageSubjectFollowCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show contentBehaviorTrackerProvider, contentEngagementTrackerProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_sheet.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show homepageRecommendationSlots;

class HomepageDetailPage extends ConsumerStatefulWidget {
  const HomepageDetailPage({
    super.key,
    required this.homepageId,
    this.selectionMode = false,
    this.initialSummary,
    this.referralSource = ReferralSource.entityPage,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
    this.feedRequestId = '',
    this.recommendationTraceId = '',
    this.experimentBucket = '',
    this.rolloutCohort = '',
    this.initialTabTarget,
  });

  final String homepageId;
  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final ReferralSource referralSource;
  final UiErrorAppearanceMode sourceAppearanceMode;
  final String feedRequestId;
  final String recommendationTraceId;
  final String experimentBucket;
  final String rolloutCohort;
  final HomepageDetailTabTarget? initialTabTarget;

  @override
  ConsumerState<HomepageDetailPage> createState() => _HomepageDetailPageState();
}

class _HomepageDetailPageState extends ConsumerState<HomepageDetailPage> {
  bool _isLoading = true;
  UiErrorSemantic? _errorSemantic;
  HomepageDetail? _detail;
  HomepageShellData? _shell;
  ObjectPageBundle? _objectPageBundle;
  HomepageIntroduction? _introduction;
  String? _viewerPersonaId;
  String? _viewerOwnerUserId;
  bool? _wishlistState;
  bool _didTrackEntityPageView = false;
  int _reviewContinuationResumeToken = 0;
  OpenHomepageReviewComposerContinuation? _lastActivatedReviewContinuation;
  CloudOperationCancellationSignal? _introductionCancellation;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _introductionCancellation?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      final justLoggedIn =
          next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated);
      if (justLoggedIn) {
        _resumeHomepageInteractionAfterLogin();
      } else if (previous?.isAuthenticated == true && !next.isAuthenticated) {
        if (_viewerPersonaId != null || _viewerOwnerUserId != null) {
          setState(() {
            _viewerPersonaId = null;
            _viewerOwnerUserId = null;
          });
        }
      }
    });
    final pendingContinuation = ref.watch(authContinuationProvider);
    if (ref.watch(authSessionControllerProvider).isAuthenticated &&
        pendingContinuation is OpenHomepageReviewComposerContinuation &&
        pendingContinuation.homepageId == widget.homepageId &&
        !identical(pendingContinuation, _lastActivatedReviewContinuation)) {
      _scheduleReviewContinuationResume(pendingContinuation);
    }
    if (_errorSemantic != null && !_isLoading) {
      return AppScaffold(
        backgroundColor: AppColors.iosPageBackground(context),
        navigationBar: AppNavigationBar(
          leading: AppNavigationBarIconButton(
            key: const ValueKey<String>('homepage-detail-error-back'),
            icon: CupertinoIcons.back,
            onPressed: _back,
          ),
          middle: const Text(ObjectHomepageText.objectHomepageDefaultTitle),
        ),
        body: AppPageErrorState(
          semantic: ensureRetryUiErrorSemantic(_errorSemantic!),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _load();
              return _errorSemantic == null
                  ? UiRecoveryOutcome.recovered
                  : UiRecoveryOutcome.stillBlocked;
            } else if (action.type == UiErrorActionType.dismiss) {
              _back();
              return UiRecoveryOutcome.handedOff;
            }
            return UiRecoveryOutcome.cancelled;
          },
        ),
      );
    }
    return HomepageDetailShell(
      recommendationSlots: homepageRecommendationSlots,
      selectionMode: widget.selectionMode,
      initialSummary: widget.initialSummary,
      isLoading: _isLoading,
      errorText: _errorSemantic?.message,
      detail: _detail,
      shell: _shell,
      objectPageBundle: _objectPageBundle,
      introductionSummary: _introduction?.summary,
      viewerPersonaId: _viewerPersonaId,
      viewerOwnerUserId: _viewerOwnerUserId,
      wishlistState: _wishlistIntentApplicable
          ? (_wishlistState ?? false)
          : null,
      initialTabTarget: widget.initialTabTarget,
      onBack: () => context.pop(),
      onShare: () => unawaited(_shareHomepage()),
      onClaim: _openClaim,
      onMaintain: _openMaintenance,
      onReport: _openStatusReport,
      onToggleFollow: _toggleHomepagePrimaryIntent,
      onMessageOwner: _openOwnerMessage,
      onCreateContent: _openCreateContent,
      onOpenIntroduction: _openIntroduction,
      onOpenRecord: _openRecord,
      onAttach: (reference) => context.pop(reference),
      onStartGathering: _wishlistIntentApplicable ? _startGatheringHere : null,
      buildRecentGatherings: _wishlistIntentApplicable
          ? ({required bool isDark}) => buildHomepageRecentGatheringsSlot(
              homepageId: widget.homepageId,
              isDark: isDark,
            )
          : null,
      onReviewsChanged: () => unawaited(_load()),
      requireReviewAuth: _requireReviewAuth,
      reviewContinuationResumeToken: _reviewContinuationResumeToken,
    );
  }

  /// 在这里发起：persona host 携实体来源引用进入 Gathering 创建。
  /// 发起不依赖交集存在；游客由创建路由的登录门与续接承接。
  void _startGatheringHere() {
    final detail = _detail;
    if (detail == null) {
      return;
    }
    unawaited(
      trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'start_gathering_here',
        pageName: AppUiSurfaces.homepageDetail.id,
        result: 'success',
        startedAt: DateTime.now(),
        homepageId: widget.homepageId,
      ),
    );
    context.push(
      AppRoutePaths.gatheringCreate,
      extra: GatheringCreateNavigationRequest(
        actionKey: 'start_gathering',
        actionLabel: ObjectHomepageText.entityActionStartGathering,
        sourceRefs: <GatheringCreateSourceReference>[
          GatheringCreateSourceReference(
            sourceRef: 'homepage',
            objectId: widget.homepageId,
            objectKind: 'homepage',
            routeId: 'homepageDetail',
          ),
        ],
        targetObject: GatheringCreateTargetObject(
          objectId: widget.homepageId,
          objectKind: 'homepage',
          objectName: detail.title,
          routeId: 'homepageDetail',
        ),
        intersection: const GatheringCreateIntersectionContext(
          intersectionId: '',
          dimension: '',
          intersectionClass: '',
        ),
        evidence: const GatheringCreateEvidenceContext(
          evidenceId: '',
          sourceRef: 'homepage',
          tagRefs: <String>[],
        ),
        referralSource: ReferralSource.entityPage,
      ),
    );
  }

  bool get _wishlistIntentApplicable =>
      _isWishlistHomepageType(_detail?.homepageType);

  bool _isWishlistHomepageType(String? homepageType) => HomepageUIConfig
      .wishlistHomepageTypes
      .contains((homepageType ?? '').trim());

  Future<bool> _requireReviewAuth() async {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      return true;
    }
    ref
        .read(authContinuationProvider.notifier)
        .set(
          OpenHomepageReviewComposerContinuation(homepageId: widget.homepageId),
        );
    await requireLogin(
      ref,
      context,
      AuthGateReason.comment,
      dismissFallback: AppRoutePaths.homepageDetail(id: widget.homepageId),
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
    return false;
  }

  /// 站外/站内分享统一入口：链接与深链均来自 metadata link 模板 codegen。
  Future<void> _shareHomepage() async {
    final detail = _detail;
    if (detail == null) {
      return;
    }
    final startedAt = DateTime.now();
    final payload = AppForwardPayload(
      kind: AppForwardSubjectKind.entityProfile,
      title: detail.title,
      subtitle: detail.subtitle ?? '',
      thumbnailUrl: detail.coverUrl ?? '',
      deeplink: AppLinkTemplates.entityHomepageAppDeepLink(widget.homepageId),
      landingUrl: ref
          .read(publicContentLinkBuilderProvider)
          .entityHomepageWebUrl(widget.homepageId),
      objectRef: MessageCardObjectRef(
        objectTypeRef: 'homepage',
        objectId: widget.homepageId,
        routeId: 'homepageDetail',
      ),
    );
    await ForwardShareSheet.show(context, payload: payload);
    if (!mounted) {
      return;
    }
    unawaited(
      trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'share_open',
        pageName: AppUiSurfaces.homepageDetail.id,
        result: 'success',
        startedAt: startedAt,
        homepageId: widget.homepageId,
      ),
    );
  }

  void _back() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.home);
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
      _wishlistState = null;
    });
    try {
      final repository = ref.read(homepageQueryProvider);
      late HomepageDetail loadedDetail;
      late HomepageShellData loadedShell;
      late ObjectPageBundle loadedBundle;
      _introductionCancellation?.cancel();
      final introductionCancellation = CloudOperationCancellationSignal();
      _introductionCancellation = introductionCancellation;
      final introductionFuture = () async {
        try {
          return await ref
              .read(homepageIntroductionRepositoryProvider)
              .getHomepageIntroduction(
                widget.homepageId,
                cancellation: introductionCancellation,
              );
        } catch (error, stackTrace) {
          if (introductionCancellation.isCancelled) {
            return null;
          }
          // 介绍是详情页的可降级附属模块；失败不得遮蔽主页主档、壳层与对象 Bundle。
          unawaited(
            ref
                .read(exceptionTelemetryPortProvider)
                .recordHandledException(
                  source: 'entity.homepage_detail.load_introduction',
                  error: error,
                  stackTrace: stackTrace,
                ),
          );
          return null;
        }
      }();
      await Future.wait<void>([
        repository.getHomepageDetail(widget.homepageId).then((d) {
          loadedDetail = d;
        }),
        repository.getHomepageShell(widget.homepageId).then((s) {
          loadedShell = s;
        }),
        repository
            .getObjectPageBundle(
              widget.homepageId,
              referralSource: widget.referralSource.value,
              feedRequestId: widget.feedRequestId,
              recommendationTraceId: widget.recommendationTraceId,
              experimentBucket: widget.experimentBucket,
              rolloutCohort: widget.rolloutCohort,
            )
            .then((bundle) {
              loadedBundle = bundle;
            }),
      ]);
      final loadedWishlistState = await _loadWishlistState(loadedDetail);
      if (!mounted) {
        return;
      }
      setState(() {
        _detail = loadedDetail;
        _shell = loadedShell;
        _objectPageBundle = loadedBundle;
        _wishlistState = loadedWishlistState;
        _isLoading = false;
      });
      _trackHomepagePageViewIfNeeded(loadedBundle, loadedDetail);
      unawaited(_hydrateViewerOwnerContext());
      final loadedIntroduction = await introductionFuture;
      if (mounted &&
          identical(_introductionCancellation, introductionCancellation)) {
        setState(() => _introduction = loadedIntroduction);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
          appearanceMode: widget.sourceAppearanceMode,
          sourceRouteId: AppRoutePaths.homepageDetailPathTemplate,
        );
        _isLoading = false;
      });
    }
  }

  Future<bool?> _loadWishlistState(HomepageDetail detail) async {
    if (!_isWishlistHomepageType(detail.homepageType)) {
      return null;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      return false;
    }
    try {
      final state = await ref
          .read(homepageDetailEntityWishlistStateReaderProvider)
          .getEntityWishlistState(
            objectId: widget.homepageId,
            objectKind: FollowSubjectKind.homepage.wireName,
          );
      return state.wishlisted;
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'entity.homepage_detail.load_wishlist_state',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      return false;
    }
  }

  Future<void> _refreshWishlistStateAfterLogin() async {
    final detail = _detail;
    if (detail == null || !_isWishlistHomepageType(detail.homepageType)) {
      return;
    }
    final state = await _loadWishlistState(detail);
    if (mounted && state != null) {
      setState(() => _wishlistState = state);
    }
  }

  Future<void> _hydrateViewerOwnerContext() async {
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      if (mounted && (_viewerPersonaId != null || _viewerOwnerUserId != null)) {
        setState(() {
          _viewerPersonaId = null;
          _viewerOwnerUserId = null;
        });
      }
      return;
    }
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      if (!mounted) return;
      final personaId = activeContext.personaId.trim();
      final ownerId = activeContext.ownerUserId.trim();
      setState(() {
        _viewerPersonaId = personaId.isEmpty ? null : personaId;
        _viewerOwnerUserId = ownerId.isEmpty ? null : ownerId;
      });
    } catch (error, stackTrace) {
      // best-effort：仅影响维护入口的 owner 判定，不阻断公开详情。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'entity.homepage_detail.load_active_persona_context',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  void _trackHomepagePageViewIfNeeded(
    ObjectPageBundle bundle,
    HomepageDetail detail,
  ) {
    if (_didTrackEntityPageView) {
      return;
    }
    final homepageId = detail.id.trim().isNotEmpty
        ? detail.id.trim()
        : bundle.objectId.trim();
    if (homepageId.isEmpty) {
      return;
    }
    _didTrackEntityPageView = true;
    ref
        .read(contentEngagementTrackerProvider)
        .trackEntityPageView(homepageId, from: widget.referralSource);
  }

  Future<void> _openClaim() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageClaim(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _openMaintenance() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageMaintenance(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _openStatusReport() async {
    final changed = await context.push<bool>(
      AppRoutePaths.homepageStatusReport(id: widget.homepageId),
    );
    if (changed == true && mounted) {
      await _load();
    }
  }

  Future<void> _toggleHomepagePrimaryIntent() async {
    final detail = _detail;
    if (detail == null) {
      return;
    }
    final usesWishlistIntent = _isWishlistHomepageType(detail.homepageType);
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      ref
          .read(authContinuationProvider.notifier)
          .set(
            usesWishlistIntent
                ? WishlistHomepageContinuation(homepageId: widget.homepageId)
                : FollowHomepageContinuation(homepageId: widget.homepageId),
          );
      await requireLogin(
        ref,
        context,
        usesWishlistIntent ? AuthGateReason.wishlist : AuthGateReason.follow,
        dismissFallback: AppRoutePaths.homepageDetail(id: widget.homepageId),
        dismissPolicy: LoginDismissPolicy.safeFallback,
      );
      return;
    }
    if (usesWishlistIntent) {
      await _toggleHomepageWishlist(detail);
      return;
    }
    await _toggleHomepageFollow(detail);
  }

  Future<void> _toggleHomepageWishlist(HomepageDetail detail) async {
    await _setHomepageWishlist(detail, wishlisted: !(_wishlistState ?? false));
  }

  Future<void> _setHomepageWishlist(
    HomepageDetail detail, {
    required bool wishlisted,
  }) async {
    final startedAt = DateTime.now();
    final tracker = ref.read(contentBehaviorTrackerProvider);
    if (wishlisted) {
      tracker.trackWishlistAdd(
        widget.homepageId,
        objectKind: FollowSubjectKind.homepage.wireName,
        displayName: detail.title,
        sourceSurface: AppUiSurfaces.homepageDetail.id,
        feedRequestId: widget.feedRequestId,
        referralSource: widget.referralSource,
      );
    } else {
      tracker.trackWishlistRemove(
        widget.homepageId,
        objectKind: FollowSubjectKind.homepage.wireName,
        sourceSurface: AppUiSurfaces.homepageDetail.id,
        feedRequestId: widget.feedRequestId,
        referralSource: widget.referralSource,
      );
    }
    await tracker.flush();
    if (!mounted) {
      return;
    }
    setState(() => _wishlistState = wishlisted);
    unawaited(
      trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: wishlisted
            ? BehaviorEventType.wishlistAdd.wireName
            : BehaviorEventType.wishlistRemove.wireName,
        pageName: AppUiSurfaces.homepageDetail.id,
        result: 'success',
        startedAt: startedAt,
        homepageId: widget.homepageId,
      ),
    );
    if (wishlisted) {
      await _showWishlistIntersectionFeedback();
    } else {
      AppToast.show(context, ObjectHomepageText.wishlistRemovedFeedback);
    }
  }

  /// 想去的即时回报（诚实两态，与沉浸页同构）：有对象交集 → 点名共同人数；
  /// 无 → 只确认「已加入想去清单」，不伪造同行者。页面内交集卡即完整证据，
  /// 不附加跳转动作。
  Future<void> _showWishlistIntersectionFeedback() async {
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
            objectBId: widget.homepageId,
            objectBType: 'homepage',
          ),
        ).future,
      );
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'entity.homepage.wishlist_intersection_feedback',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
    if (!mounted) {
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
    );
  }

  Future<void> _toggleHomepageFollow(HomepageDetail detail) async {
    final startedAt = DateTime.now();
    try {
      // 关注关系唯一归属 user.SubjectFollow 聚合（B6 裁决 1）；
      // Homepage 不再提供 follow 写入口。
      final writer = ref.read(homepageSubjectFollowCommandWriterProvider);
      final following = detail.viewerFollowsHomepage;
      final result = following
          ? await writer.unfollow(
              UnfollowSubjectCommand(
                subjectType: SubjectFollowTargetKind.homepage,
                subjectId: widget.homepageId,
              ),
            )
          : await writer.follow(
              FollowSubjectCommand(
                subjectType: SubjectFollowTargetKind.homepage,
                subjectId: widget.homepageId,
                source: widget.referralSource.value,
              ),
            );
      if (!mounted) {
        return;
      }
      final resultFollowing = result.state == SubjectFollowState.following;
      final delta = resultFollowing == following
          ? 0
          : (resultFollowing ? 1 : -1);
      setState(
        () => _detail = detail.copyWith(
          viewerFollowsHomepage: resultFollowing,
          followerCount: (detail.followerCount + delta).clamp(0, 1 << 31),
        ),
      );
      unawaited(
        trackHomepageProductAction(
          ref.read(journeyEventTrackerProvider),
          action: resultFollowing ? 'follow' : 'unfollow',
          pageName: AppUiSurfaces.homepageDetail.id,
          result: 'success',
          startedAt: startedAt,
          homepageId: widget.homepageId,
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
      unawaited(
        trackHomepageProductAction(
          ref.read(journeyEventTrackerProvider),
          action: detail.viewerFollowsHomepage ? 'unfollow' : 'follow',
          pageName: AppUiSurfaces.homepageDetail.id,
          result: 'failure',
          startedAt: startedAt,
          homepageId: widget.homepageId,
          error: error,
        ),
      );
    }
  }

  /// 私信 Owner：进入 owner 主页并立即执行主页既有的「私信 / 打招呼」
  /// 关系能力位分流（canOpen→会话 / canGreet→打招呼 / pending→提示）。
  /// 陌生人破冰、`greeting_required` 门禁与登录续接全部复用主页实现，
  /// 实体侧不再直建会话绕过 conversation-entry 矩阵。
  void _openOwnerMessage() {
    final ownerPersonaId =
        (_detail?.ownerPersonaId?.trim().isNotEmpty == true
                ? _detail!.ownerPersonaId
                : _detail?.ownerUserId)
            ?.trim();
    if (ownerPersonaId == null || ownerPersonaId.isEmpty) {
      return;
    }
    unawaited(
      trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'message_owner',
        pageName: AppUiSurfaces.homepageDetail.id,
        result: 'success',
        startedAt: DateTime.now(),
        homepageId: widget.homepageId,
      ),
    );
    context.push(
      AppRoutePaths.userProfile(userHandle: ownerPersonaId),
      extra: UserProfileRouteExtra(
        personaId: ownerPersonaId,
        openMessageComposer: true,
      ),
    );
  }

  void _resumeHomepageInteractionAfterLogin() {
    if (!mounted) {
      return;
    }
    unawaited(_hydrateViewerOwnerContext());
    final pending = ref.read(authContinuationProvider);
    final controller = ref.read(authContinuationProvider.notifier);
    if (pending is WishlistHomepageContinuation &&
        pending.homepageId == widget.homepageId) {
      final wishlist = controller.take<WishlistHomepageContinuation>();
      final detail = _detail;
      if (wishlist != null && detail != null) {
        unawaited(_setHomepageWishlist(detail, wishlisted: true));
      } else if (wishlist != null) {
        controller.set(wishlist);
      }
      return;
    }
    unawaited(_refreshWishlistStateAfterLogin());
    if (pending is OpenHomepageReviewComposerContinuation &&
        pending.homepageId == widget.homepageId) {
      _scheduleReviewContinuationResume(pending);
      return;
    }
    final follow = controller.take<FollowHomepageContinuation>();
    if (follow != null) {
      if (follow.homepageId == widget.homepageId) {
        unawaited(_toggleHomepagePrimaryIntent());
      } else {
        controller.set(follow);
      }
      return;
    }
  }

  void _scheduleReviewContinuationResume(
    OpenHomepageReviewComposerContinuation continuation,
  ) {
    _lastActivatedReviewContinuation = continuation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          !identical(ref.read(authContinuationProvider), continuation)) {
        return;
      }
      setState(() => _reviewContinuationResumeToken += 1);
    });
  }

  void _openCreateContent(HomepageCanonicalReference reference) {
    context.push(
      AppRoutePaths.create(),
      extra: CreateEntryArguments(homepage: reference),
    );
  }

  void _openIntroduction() {
    context.push(
      AppRoutePaths.homepageIntroduction(
        id: widget.homepageId,
        source: widget.referralSource.value,
      ),
    );
  }

  void _openRecord(HomepageContentPreview item) {
    final postId = item.postId.trim();
    if (postId.isEmpty) {
      return;
    }
    final contentType = (item.contentType ?? '').trim();
    final feedRequestId = widget.feedRequestId.trim();
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(
          postId,
          contentType: contentType.isEmpty ? null : contentType,
          feedRequestId: feedRequestId.isEmpty ? null : feedRequestId,
          referralSource: ReferralSource.entityPage,
        );
    context.push(
      AppRoutePaths.workBrowser(
        workId: postId,
        filter: contentType.isEmpty ? null : contentType,
        source: ReferralSource.entityPage.value,
        sourceTheme: uiErrorAppearanceRouteValueFor(context),
      ),
      extra: WorkBrowserEntryRouteExtra(
        referralSource: ReferralSource.entityPage,
        feedRequestId: feedRequestId.isEmpty ? null : feedRequestId,
      ),
    );
  }
}
