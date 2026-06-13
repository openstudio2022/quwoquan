import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_detail_shell.dart';

class HomepageDetailPage extends ConsumerStatefulWidget {
  const HomepageDetailPage({
    super.key,
    required this.homepageId,
    this.selectionMode = false,
    this.initialSummary,
    this.referralSource = ReferralSource.entityPage,
    this.feedRequestId = '',
    this.recommendationTraceId = '',
    this.experimentBucket = '',
    this.rolloutCohort = '',
  });

  final String homepageId;
  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final ReferralSource referralSource;
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
      onCreateContent: _openCreateContent,
      onOpenIntroduction: _openIntroduction,
      onAttach: (reference) => context.pop(reference),
      onIntersectionReasonTap: _handleIntersectionReasonTap,
    );
  }

  void _handleIntersectionReasonTap(IntersectionReason reason) {
    if (reason.actionType.trim() == 'ask_xiaoqu') {
      _openAssistantForIntersection(reason);
      return;
    }
    _trackIntersectionReasonTap(reason);
  }

  void _trackIntersectionReasonTap(IntersectionReason reason) {
    final targetId = reason.actionTargetId.trim().isEmpty
        ? widget.homepageId
        : reason.actionTargetId.trim();
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(
          targetId,
          referralSource: widget.referralSource,
          intersectionId: reason.intersectionId,
          intersectionDimension: reason.dimension,
          intersectionClass: reason.intersectionClass,
          intersectionTagRefs: reason.tagRefs,
        );
  }

  void _openAssistantForIntersection(IntersectionReason reason) {
    _trackIntersectionReasonTap(reason);
    final target = VisitTarget.page('homepage_detail_${widget.homepageId}');
    final entityId =
        _objectPageBundle?.canonicalEntityId.trim().isNotEmpty == true
            ? _objectPageBundle!.canonicalEntityId.trim()
            : (_detail?.canonicalEntityId?.trim() ?? widget.homepageId);
    final openContext = AssistantOpenContext(
      source: AssistantSource.profile,
      tab: 'object_intersection',
      dimension: reason.dimension,
      entityId: entityId,
      objectType: 'homepage',
      intersectionRefs: _intersectionRefsFor(reason),
      visitTarget: target,
      experienceLevel: ref
          .read(visitRecorderServiceProvider)
          .getExperience(target),
      hints: <String, dynamic>{
        'intersectionId': reason.intersectionId,
        'primaryText': reason.primaryText,
        'actionType': reason.actionType,
        'objectTitle': _shell?.homepage.title ?? _detail?.title ?? '',
      },
    );
    context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  List<String> _intersectionRefsFor(IntersectionReason reason) {
    final refs = <String>{
      if (reason.intersectionId.trim().isNotEmpty)
        'intersection:${reason.intersectionId.trim()}',
      ...reason.tagRefs.map((tag) => tag.trim()).where((tag) => tag.isNotEmpty),
    };
    return refs.toList(growable: false);
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
