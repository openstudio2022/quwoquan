import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_ui_config.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/content/content/post/domain/create_entry_arguments.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_action_observability.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_tab.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_detail_shell.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_share_sheet.dart';

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
        if (_viewerOwnerUserId != null) {
          setState(() => _viewerOwnerUserId = null);
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
      selectionMode: widget.selectionMode,
      initialSummary: widget.initialSummary,
      isLoading: _isLoading,
      errorText: _errorSemantic?.message,
      detail: _detail,
      shell: _shell,
      objectPageBundle: _objectPageBundle,
      introductionSummary: _introduction?.summary,
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
      onReviewsChanged: () => unawaited(_load()),
      requireReviewAuth: _requireReviewAuth,
      reviewContinuationResumeToken: _reviewContinuationResumeToken,
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
      landingUrl: AppPublicContentLinks.entityHomepageWebUrl(widget.homepageId),
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
        ref,
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
            AppExceptionTelemetryService.instance.recordHandledException(
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
        AppExceptionTelemetryService.instance.recordHandledException(
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
      if (mounted && _viewerOwnerUserId != null) {
        setState(() => _viewerOwnerUserId = null);
      }
      return;
    }
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      if (!mounted) return;
      final ownerId = activeContext.ownerUserId.trim();
      setState(() => _viewerOwnerUserId = ownerId.isEmpty ? null : ownerId);
    } catch (error, stackTrace) {
      // best-effort：仅影响维护入口的 owner 判定，不阻断公开详情。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
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
        ref,
        action: wishlisted
            ? BehaviorEventType.wishlistAdd.wireName
            : BehaviorEventType.wishlistRemove.wireName,
        pageName: AppUiSurfaces.homepageDetail.id,
        result: 'success',
        startedAt: startedAt,
        homepageId: widget.homepageId,
      ),
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
                subjectType: FollowSubjectKind.homepage,
                subjectId: widget.homepageId,
              ),
            )
          : await writer.follow(
              FollowSubjectCommand(
                subjectType: FollowSubjectKind.homepage,
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
          ref,
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
          ref,
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

  Future<void> _openOwnerMessage() async {
    final ownerPersonaId =
        (_detail?.ownerPersonaId?.trim().isNotEmpty == true
                ? _detail!.ownerPersonaId
                : _detail?.ownerUserId)
            ?.trim();
    if (ownerPersonaId == null || ownerPersonaId.isEmpty) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      ref
          .read(authContinuationProvider.notifier)
          .set(
            OpenHomepageOwnerConversationContinuation(
              homepageId: widget.homepageId,
              ownerPersonaId: ownerPersonaId,
            ),
          );
      await requireLogin(
        ref,
        context,
        AuthGateReason.sendMessage,
        dismissFallback: AppRoutePaths.homepageDetail(id: widget.homepageId),
        dismissPolicy: LoginDismissPolicy.safeFallback,
      );
      return;
    }
    final startedAt = DateTime.now();
    try {
      final created = await ref
          .read(chatConversationRepositoryProvider)
          .createConversation(
            type: 'direct',
            initialMemberIds: <String>[ownerPersonaId],
          );
      if (!mounted || created.conversationId.isEmpty) {
        return;
      }
      unawaited(
        trackHomepageProductAction(
          ref,
          action: 'message_owner',
          pageName: AppUiSurfaces.homepageDetail.id,
          result: 'success',
          startedAt: startedAt,
          homepageId: widget.homepageId,
        ),
      );
      context.push(AppRoutePaths.chatDetail(id: created.conversationId));
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
          ref,
          action: 'message_owner',
          pageName: AppUiSurfaces.homepageDetail.id,
          result: 'failure',
          startedAt: startedAt,
          homepageId: widget.homepageId,
          error: error,
        ),
      );
    }
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
    final message = controller
        .take<OpenHomepageOwnerConversationContinuation>();
    if (message == null) {
      return;
    }
    if (message.homepageId == widget.homepageId) {
      unawaited(_openOwnerMessage());
    } else {
      controller.set(message);
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
