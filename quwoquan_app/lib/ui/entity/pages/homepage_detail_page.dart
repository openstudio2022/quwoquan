import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_detail_shell.dart';

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
  bool _didTrackEntityPageView = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  Widget build(BuildContext context) {
    if (_errorSemantic != null && !_isLoading) {
      return AppPageErrorState(
        semantic: _errorSemantic!,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _load();
          }
        },
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
      onBack: () => context.pop(),
      onClaim: _openClaim,
      onMaintain: _openMaintenance,
      onReport: _openStatusReport,
      onToggleFollow: _toggleHomepageFollow,
      onMessageOwner: _openOwnerMessage,
      onCreateContent: _openCreateContent,
      onOpenIntroduction: _openIntroduction,
      onAttach: (reference) => context.pop(reference),
    );
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
    });
    try {
      final repository = ref.read(homepageRepositoryProvider);
      late HomepageDetail loadedDetail;
      late HomepageShellData loadedShell;
      late ObjectPageBundle loadedBundle;
      HomepageIntroduction? loadedIntroduction;
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
        ref
            .read(homepageIntroductionRepositoryProvider)
            .getHomepageIntroduction(widget.homepageId)
            .then((introduction) {
              loadedIntroduction = introduction;
            }),
      ]);
      ActivePersonaContextViewData? activeContext;
      try {
        activeContext = await ref.read(activePersonaContextProvider.future);
      } catch (_) {
        activeContext = null;
      }
      if (!mounted) {
        return;
      }
      final ownerId = activeContext?.ownerUserId.trim() ?? '';
      setState(() {
        _detail = loadedDetail;
        _shell = loadedShell;
        _objectPageBundle = loadedBundle;
        _introduction = loadedIntroduction;
        _viewerOwnerUserId = ownerId.isEmpty ? null : ownerId;
        _isLoading = false;
      });
      _trackCanonicalEntityPageViewIfNeeded(loadedBundle, loadedDetail);
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

  void _trackCanonicalEntityPageViewIfNeeded(
    ObjectPageBundle bundle,
    HomepageDetail detail,
  ) {
    if (_didTrackEntityPageView) {
      return;
    }
    final entityId = bundle.canonicalEntityId.trim().isNotEmpty
        ? bundle.canonicalEntityId.trim()
        : (detail.canonicalEntityId?.trim() ?? '');
    if (entityId.isEmpty) {
      return;
    }
    _didTrackEntityPageView = true;
    ref
        .read(contentEngagementTrackerProvider)
        .trackEntityPageView(entityId, from: widget.referralSource);
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

  Future<void> _toggleHomepageFollow() async {
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      await requireLogin(ref, context, AuthGateReason.follow);
      if (!mounted ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
    }
    final detail = _detail;
    if (detail == null) {
      return;
    }
    try {
      final repository = ref.read(homepageRepositoryProvider);
      final next = detail.viewerFollowsHomepage
          ? await repository.unfollowHomepage(widget.homepageId)
          : await repository.followHomepage(widget.homepageId);
      if (!mounted) {
        return;
      }
      setState(() => _detail = next);
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
    }
  }

  Future<void> _openOwnerMessage() async {
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      await requireLogin(
        ref,
        context,
        AuthGateReason.sendMessage,
        dismissFallback: AppRoutePaths.home,
      );
      if (!mounted ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
    }
    final ownerSubAccountId =
        (_detail?.ownerSubAccountId?.trim().isNotEmpty == true
                ? _detail!.ownerSubAccountId
                : _detail?.ownerUserId)
            ?.trim();
    if (ownerSubAccountId == null || ownerSubAccountId.isEmpty) {
      return;
    }
    try {
      final created = await ref
          .read(chatRepositoryProvider)
          .createConversation(
            type: 'direct',
            initialMemberIds: <String>[ownerSubAccountId],
          );
      if (!mounted || created.conversationId.isEmpty) {
        return;
      }
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
    }
  }

  void _openCreateContent(HomepageCanonicalReference reference) {
    context.push(AppRoutePaths.create(), extra: reference);
  }

  void _openIntroduction() {
    context.push(
      AppRoutePaths.homepageIntroduction(
        id: widget.homepageId,
        source: widget.referralSource.value,
      ),
    );
  }
}
