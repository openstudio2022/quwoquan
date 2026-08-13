import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_page_copy.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_widgets.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show exceptionTelemetryPortProvider;
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart'
    show GatheringText;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show
        gatheringDetailGatheringPostsReaderProvider,
        gatheringDetailSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show GatheringSocialProofSummary;

class GatheringDetailPage extends ConsumerStatefulWidget {
  const GatheringDetailPage({
    super.key,
    required this.gatheringId,
    required this.copy,
    this.onEnterChat,
    this.onPublishRecap,
    this.onOpenRecapPost,
  });

  static const viewKey = ValueKey<String>('gathering-detail-page');
  static const loadingKey = ValueKey<String>('gathering-detail-loading');
  static const emptyKey = ValueKey<String>('gathering-detail-empty');
  static const primaryActionKey = ValueKey<String>(
    'gathering-detail-primary-action',
  );
  static const privatePlaceKey = ValueKey<String>(
    'gathering-detail-private-place',
  );
  static const hostConsoleKey = ValueKey<String>('gathering-host-console');
  static const sharedExperienceKey = ValueKey<String>(
    'gathering-shared-experience',
  );
  static const publishRecapKey = ValueKey<String>(
    'gathering-publish-recap',
  );
  static const organizerStatsKey = ValueKey<String>(
    'gathering-organizer-stats',
  );

  static ValueKey<String> approveKey(String personaId) =>
      ValueKey<String>('gathering-approve-$personaId');

  static ValueKey<String> rejectKey(String personaId) =>
      ValueKey<String>('gathering-reject-$personaId');

  static ValueKey<String> removeKey(String personaId) =>
      ValueKey<String>('gathering-remove-$personaId');

  final String gatheringId;
  final GatheringDetailPageCopy copy;
  final ValueChanged<String>? onEnterChat;

  /// 发布回顾入口：携带 (gatheringId, gatheringTitle) 进入创作流。
  final void Function(String gatheringId, String gatheringTitle)?
  onPublishRecap;

  /// 打开一条共同经历回顾内容（postId）。
  final ValueChanged<String>? onOpenRecapPost;

  @override
  ConsumerState<GatheringDetailPage> createState() =>
      _GatheringDetailPageState();
}

class _GatheringDetailPageState extends ConsumerState<GatheringDetailPage> {
  final TextEditingController _invitePersonaController =
      TextEditingController();
  final TextEditingController _capacityController = TextEditingController();
  final TextEditingController _reasonController = TextEditingController();
  final Set<String> _busyActions = <String>{};

  GatheringDetailPresentationSlice? _detail;
  GatheringOutcomeStatus _selectedOutcome = GatheringOutcomeStatus.unverified;
  Object? _loadError;
  Object? _actionError;
  bool _loading = true;

  // 共同经历聚合区：公开回顾内容与加载状态。读取失败只影响本区块，
  // 不阻断详情主体；不伪造空列表成功态。
  List<ContentPostViewData>? _recapPosts;
  bool _recapLoading = false;

  // 发起人往绩（四锚点 organizer 锚点两级诚实计数）；读取失败或零发起
  // 不渲染，不伪造。
  GatheringSocialProofSummary? _organizerStats;

  Color get _primaryTextColor => AppColorsFunctional.getColor(
    CupertinoTheme.of(context).brightness == Brightness.dark,
    ColorType.foregroundPrimary,
  );

  Color get _secondaryTextColor => AppColorsFunctional.getColor(
    CupertinoTheme.of(context).brightness == Brightness.dark,
    ColorType.foregroundSecondary,
  );

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(covariant GatheringDetailPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.gatheringId != widget.gatheringId) {
      _detail = null;
      _loadError = null;
      _actionError = null;
      _loading = true;
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _invitePersonaController.dispose();
    _capacityController.dispose();
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _loadError = null;
      });
    }
    try {
      final reader = ref.read(gatheringQueryReaderProvider);
      final result = await reader.getDetail(
        GatheringDetailQuery(gatheringId: widget.gatheringId),
      );
      if (!mounted) return;
      setState(() {
        _detail = result;
        _loading = false;
        final maxParticipants = result?.publicDetail.capacity.maxParticipants;
        if (maxParticipants != null) {
          _capacityController.text = maxParticipants.toString();
        }
      });
      if (result != null) {
        unawaited(_loadRecapPosts());
        unawaited(_loadOrganizerStats(result));
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = error;
      });
    }
  }

  String _idempotencyKey(
    GatheringPublicDetailSlice detail,
    String action, [
    String target = '',
  ]) {
    return '${detail.gatheringId}:${detail.aggregateVersion}:$action:$target';
  }

  Future<void> _runAction(
    String action,
    Future<GatheringCommandResult> Function(
      GatheringCommandWriter writer,
      GatheringDetailPresentationSlice detail,
    )
    operation,
  ) async {
    final detail = _detail;
    if (detail == null || _busyActions.contains(action)) return;
    setState(() {
      _busyActions.add(action);
      _actionError = null;
    });
    try {
      final writer = ref.read(gatheringCommandWriterProvider);
      await operation(writer, detail);
      // 漏斗辅证埋点（product_action 轨）：只记成功事实；分子分母真相源
      // 仍是域事实投影，埋点失败不阻断主流程。
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'gathering_flywheel',
              action: 'gathering_${action.replaceAll('-', '_')}_succeeded',
              pageName: 'gathering_detail',
              targetType: 'gathering',
              targetKey: detail.publicDetail.gatheringId,
            ),
      );
      if (!mounted) return;
      setState(() => _busyActions.remove(action));
      await _load();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _busyActions.remove(action);
        _actionError = error;
      });
    }
  }

  Future<void> _runPrimaryAction() async {
    final detail = _detail;
    if (detail == null) return;
    final public = detail.publicDetail;
    final participation = public.viewerParticipation;
    switch (public.primaryAction) {
      case GatheringPrimaryAction.join:
        await _runAction(
          'join',
          (writer, value) => writer.joinOpen(
            GatheringParticipationCommandInput(
              idempotencyKey: _idempotencyKey(public, 'join'),
              gatheringId: public.gatheringId,
              expectedGatheringVersion: public.aggregateVersion,
              expectedParticipationVersion: participation?.version ?? 0,
            ),
          ),
        );
      case GatheringPrimaryAction.apply:
        await _runAction(
          'apply',
          (writer, value) => writer.apply(
            GatheringApplyInput(
              idempotencyKey: _idempotencyKey(public, 'apply'),
              gatheringId: public.gatheringId,
              expectedGatheringVersion: public.aggregateVersion,
              expectedParticipationVersion: participation?.version ?? 0,
            ),
          ),
        );
      case GatheringPrimaryAction.acceptInvitation:
        await _runAction(
          'accept-invitation',
          (writer, value) => writer.acceptInvitation(
            GatheringParticipationCommandInput(
              idempotencyKey: _idempotencyKey(public, 'accept-invitation'),
              gatheringId: public.gatheringId,
              expectedGatheringVersion: public.aggregateVersion,
              expectedParticipationVersion: participation?.version ?? 0,
            ),
          ),
        );
      case GatheringPrimaryAction.watchAvailability:
        await _runAction(
          'watch-availability',
          (writer, value) => writer.watchAvailability(
            GatheringAvailabilityWatchCommandInput(
              idempotencyKey: _idempotencyKey(public, 'watch-availability'),
              gatheringId: public.gatheringId,
              expectedGatheringVersion: public.aggregateVersion,
              expectedWatchVersion: 0,
            ),
          ),
        );
      case GatheringPrimaryAction.enterChat:
        final conversationId = public.conversationId?.trim();
        if (conversationId != null && conversationId.isNotEmpty) {
          widget.onEnterChat?.call(conversationId);
        }
      case GatheringPrimaryAction.readOnly || GatheringPrimaryAction.noAction:
        return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final background = AppColors.iosPageBackground(context);
    return AppScaffold(
      key: GatheringDetailPage.viewKey,
      backgroundColor: background,
      navigationBar: AppNavigationBar(
        backgroundColor: background,
        middle: Text(widget.copy.pageTitle),
      ),
      body: _buildBody(),
    );
  }

  Future<void> _loadRecapPosts() async {
    if (_recapLoading) return;
    setState(() => _recapLoading = true);
    try {
      final page = await ref
          .read(gatheringDetailGatheringPostsReaderProvider)
          .listPostsByGathering(gatheringId: widget.gatheringId);
      if (!mounted) return;
      setState(() {
        _recapPosts = page.items;
        _recapLoading = false;
      });
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering_detail.load_recap_posts',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      if (!mounted) return;
      // 读取失败保持 _recapPosts == null：区块不渲染，不伪造空态。
      setState(() => _recapLoading = false);
    }
  }

  Future<void> _loadOrganizerStats(
    GatheringDetailPresentationSlice detail,
  ) async {
    final host = detail.publicDetail.host;
    if (host.subjectKind != GatheringHostSubjectKind.persona ||
        host.subjectId.trim().isEmpty) {
      return;
    }
    try {
      final stats = await ref
          .read(gatheringDetailSocialProofReaderProvider)
          .getGatheringSocialProof(
            anchorKind: 'organizer',
            objectId: host.subjectId.trim(),
          );
      if (!mounted) return;
      setState(() => _organizerStats = stats);
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering_detail.load_organizer_stats',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  Widget _buildBody() {
    if (_loading) {
      return Center(
        key: GatheringDetailPage.loadingKey,
        child: AppRequestFeedback.section(),
      );
    }
    final loadError = _loadError;
    if (loadError != null) {
      return AppPageErrorState(
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: loadError,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          ),
          retryLabel: widget.copy.retryAction,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _load();
            return _loadError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    final detail = _detail;
    if (detail == null) {
      return Center(
        key: GatheringDetailPage.emptyKey,
        child: Semantics(
          liveRegion: true,
          label: widget.copy.emptyTitle,
          child: Text(
            widget.copy.emptyTitle,
            style: TextStyle(
              color: _secondaryTextColor,
              fontSize: AppTypography.base,
            ),
          ),
        ),
      );
    }

    return GatheringPageBody(
      bottom: _primaryAction(detail),
      children: <Widget>[
        _publicDetail(detail),
        ..._sharedExperienceSection(detail),
        if (detail.privateDetail?.authority.hasHostConsole ??
            false) ...<Widget>[
          SizedBox(height: AppSpacing.interGroupMd),
          _hostConsole(detail),
        ],
        if (_actionError != null) ...<Widget>[
          SizedBox(height: AppSpacing.interGroupMd),
          AppSectionErrorCard(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: _actionError!,
                category: UiErrorCategory.backgroundAction,
                scope: UiErrorScope.section,
              ),
              retryLabel: widget.copy.retryAction,
            ),
            margin: EdgeInsets.zero,
            onAction: (_) async => _load(),
          ),
        ],
      ],
    );
  }

  Widget _publicDetail(GatheringDetailPresentationSlice detail) {
    final public = detail.publicDetail;
    final exactPlace = detail.visibleExactMeetingPoint;
    final requirements = public.purpose.requirementLabels.isEmpty
        ? widget.copy.noRequirements
        : public.purpose.requirementLabels.join('\n');
    final policy = <String>[
      widget.copy.audience(public.policy.audience),
      widget.copy.admission(public.policy.admission),
    ].join('\n');
    final schedule = <String>[
      if (public.schedule.startAt != null)
        public.schedule.startAt!.toIso8601String(),
      if (public.schedule.endAt != null)
        public.schedule.endAt!.toIso8601String(),
      public.schedule.timezone,
    ].join('\n');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          header: true,
          child: Text(
            public.purpose.title,
            style: TextStyle(
              color: _primaryTextColor,
              fontSize: AppTypography.xxl,
              fontWeight: AppTypography.bold,
            ),
          ),
        ),
        if (public.purpose.summary.trim().isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            public.purpose.summary,
            style: TextStyle(
              color: _secondaryTextColor,
              fontSize: AppTypography.base,
              height: AppTypography.lineHeightRelaxed,
            ),
          ),
        ],
        SizedBox(height: AppSpacing.interGroupMd),
        GatheringSectionCard(
          title: widget.copy.pageTitle,
          child: Column(
            children: <Widget>[
              GatheringFactRow(
                label: widget.copy.hostLabel,
                value: public.host.displayName,
              ),
              if ((_organizerStats?.publishedCount ?? 0) > 0)
                GatheringFactRow(
                  key: GatheringDetailPage.organizerStatsKey,
                  label: widget.copy.organizerStatsLabel,
                  value: GatheringText.detailOrganizerStats(
                    _organizerStats!.publishedCount.toInt(),
                    _organizerStats!.formedCount.toInt(),
                    _organizerStats!.experiencedCount.toInt(),
                  ),
                ),
              GatheringFactRow(label: widget.copy.timeLabel, value: schedule),
              GatheringFactRow(
                label: widget.copy.placeLabel,
                value: public.place.coarsePlaceLabel,
              ),
              if (exactPlace != null)
                GatheringFactRow(
                  key: GatheringDetailPage.privatePlaceKey,
                  label: widget.copy.privatePlaceLabel,
                  value: exactPlace,
                ),
              GatheringFactRow(
                label: widget.copy.capacityLabel,
                value:
                    '${public.capacity.occupiedSeats}/${public.capacity.maxParticipants}',
              ),
              GatheringFactRow(label: widget.copy.policyLabel, value: policy),
              GatheringFactRow(
                label: widget.copy.requirementsLabel,
                value: requirements,
              ),
              GatheringFactRow(
                label: widget.copy.revisionsLabel,
                value: public.revisions.length.toString(),
              ),
              if (public.outcomeStatus != null)
                GatheringFactRow(
                  label: widget.copy.outcomeAction,
                  value: widget.copy.outcome(public.outcomeStatus!),
                ),
            ],
          ),
        ),
      ],
    );
  }

  /// 共同经历聚合区三态（诚实红线）：
  /// - ≥2 名不同作者公开关联 → 「共同经历」聚合列表；
  /// - 仅 1 名作者 → 「个人回顾」；
  /// - 0 条且行动时间已结束 → 「行动时间已结束」，不伪造内容。
  /// 行动未结束且无内容时不渲染区块；读取失败也不渲染（不冒充空态）。
  /// active 参与者始终看到「发布回顾」入口。
  List<Widget> _sharedExperienceSection(
    GatheringDetailPresentationSlice detail,
  ) {
    final public = detail.publicDetail;
    final viewerActive =
        public.viewerParticipation?.state == GatheringParticipationState.active;
    final posts = _recapPosts;
    final ended = public.temporalPhase == GatheringTemporalPhase.ended ||
        public.lifecycleStatus == GatheringLifecycleStatus.completed;
    if (posts == null) {
      // 未加载成功：只在 active 参与者场景保留发布入口，不渲染聚合态。
      if (!viewerActive) return const <Widget>[];
      return <Widget>[
        SizedBox(height: AppSpacing.interGroupMd),
        _publishRecapButton(public),
      ];
    }
    final distinctAuthors = posts
        .map((post) => post.authorId.trim())
        .where((authorId) => authorId.isNotEmpty)
        .toSet();
    final hasSharedExperience = distinctAuthors.length >= 2;
    if (posts.isEmpty && !ended && !viewerActive) {
      return const <Widget>[];
    }
    final title = hasSharedExperience
        ? widget.copy.sharedExperienceTitle
        : widget.copy.sharedExperienceSingleTitle;
    return <Widget>[
      SizedBox(height: AppSpacing.interGroupMd),
      GatheringSectionCard(
        key: GatheringDetailPage.sharedExperienceKey,
        title: posts.isEmpty ? widget.copy.sharedExperienceTitle : title,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (posts.isEmpty)
              Text(
                widget.copy.sharedExperienceEndedEmpty,
                style: TextStyle(
                  color: _secondaryTextColor,
                  fontSize: AppTypography.base,
                ),
              )
            else
              for (final post in posts) _recapPostRow(post),
            if (viewerActive) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              _publishRecapButton(public),
            ],
          ],
        ),
      ),
    ];
  }

  Widget _recapPostRow(ContentPostViewData post) {
    final label = post.title.trim().isNotEmpty
        ? post.title.trim()
        : post.normalizedBody.trim();
    return CupertinoButton(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      onPressed: widget.onOpenRecapPost == null
          ? null
          : () => widget.onOpenRecapPost!(post.id),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: _primaryTextColor,
                    fontSize: AppTypography.base,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  post.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: _secondaryTextColor,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppTypography.base,
            color: _secondaryTextColor,
          ),
        ],
      ),
    );
  }

  Widget _publishRecapButton(GatheringPublicDetailSlice public) {
    return Semantics(
      button: true,
      label: widget.copy.recapAction,
      child: CupertinoButton(
        key: GatheringDetailPage.publishRecapKey,
        padding: EdgeInsets.zero,
        onPressed: widget.onPublishRecap == null
            ? null
            : () => widget.onPublishRecap!(
                widget.gatheringId,
                public.purpose.title,
              ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.square_pencil,
              size: AppTypography.base,
              color: AppColors.primaryColor,
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Text(
              widget.copy.recapAction,
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.base,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget? _primaryAction(GatheringDetailPresentationSlice detail) {
    final action = detail.publicDetail.primaryAction;
    if (action == GatheringPrimaryAction.noAction) return null;
    final enabled =
        action != GatheringPrimaryAction.readOnly &&
        !_busyActions.contains(_actionId(action));
    return Semantics(
      button: true,
      enabled: enabled,
      label: widget.copy.primaryAction(action),
      child: SizedBox(
        width: double.infinity,
        child: CupertinoButton.filled(
          key: GatheringDetailPage.primaryActionKey,
          onPressed: enabled ? () => unawaited(_runPrimaryAction()) : null,
          child: _busyActions.contains(_actionId(action))
              ? AppRequestFeedback.inline(indicatorColor: CupertinoColors.white)
              : Text(widget.copy.primaryAction(action)),
        ),
      ),
    );
  }

  String _actionId(GatheringPrimaryAction action) => switch (action) {
    GatheringPrimaryAction.join => 'join',
    GatheringPrimaryAction.apply => 'apply',
    GatheringPrimaryAction.acceptInvitation => 'accept-invitation',
    GatheringPrimaryAction.watchAvailability => 'watch-availability',
    GatheringPrimaryAction.enterChat => 'enter-chat',
    GatheringPrimaryAction.readOnly => 'read-only',
    GatheringPrimaryAction.noAction => 'no-action',
  };

  Widget _hostConsole(GatheringDetailPresentationSlice detail) {
    final private = detail.privateDetail!;
    final authority = private.authority;
    return Container(
      key: GatheringDetailPage.hostConsoleKey,
      child: GatheringSectionCard(
        title: widget.copy.hostConsoleTitle,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (authority.canReviewApplications)
              _applicationConsole(detail, private),
            if (authority.canInvite) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              _inviteConsole(detail),
            ],
            if (authority.canRemoveParticipants) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              _rosterConsole(detail, private),
            ],
            if (authority.canChangeCapacity) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              GatheringLabeledTextField(
                label: widget.copy.capacityLabel,
                controller: _capacityController,
                placeholder: widget.copy.capacityLabel,
                keyboardType: TextInputType.number,
              ),
              _consoleButton(
                key: const ValueKey<String>('gathering-change-capacity'),
                label: widget.copy.capacityAction,
                actionId: 'change-capacity',
                onPressed: () => _changeCapacity(detail),
              ),
            ],
            if (authority.canChangeAdmission)
              _consoleButton(
                key: const ValueKey<String>('gathering-change-admission'),
                label: private.admissionPaused
                    ? widget.copy.resumeAdmissionAction
                    : widget.copy.pauseAdmissionAction,
                actionId: 'change-admission',
                onPressed: () => _changeAdmission(detail, private),
              ),
            if (authority.canUpdateMaterialDetails)
              _consoleButton(
                key: const ValueKey<String>('gathering-material-update'),
                label: widget.copy.materialUpdateAction,
                actionId: 'material-update',
                onPressed: () => _materialUpdate(detail, private),
              ),
            if (authority.canCancel ||
                authority.canStart ||
                authority.canRecordOutcome) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              GatheringLabeledTextField(
                label: widget.copy.reasonLabel,
                controller: _reasonController,
                placeholder: widget.copy.reasonLabel,
              ),
            ],
            if (authority.canCancel)
              _consoleButton(
                key: const ValueKey<String>('gathering-cancel'),
                label: widget.copy.cancelAction,
                actionId: 'cancel',
                onPressed: () => _cancel(detail),
              ),
            if (authority.canStart)
              _consoleButton(
                key: const ValueKey<String>('gathering-start'),
                label: widget.copy.startAction,
                actionId: 'start',
                onPressed: () => _start(detail),
              ),
            if (authority.canRecordOutcome) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              GatheringChoiceField<GatheringOutcomeStatus>(
                label: widget.copy.outcomeAction,
                value: _selectedOutcome,
                choices: GatheringOutcomeStatus.values
                    .map(
                      (value) => GatheringChoice<GatheringOutcomeStatus>(
                        value: value,
                        label: widget.copy.outcome(value),
                      ),
                    )
                    .toList(growable: false),
                onChanged: (value) => setState(() => _selectedOutcome = value),
              ),
              _consoleButton(
                key: const ValueKey<String>('gathering-outcome'),
                label: widget.copy.outcomeAction,
                actionId: 'outcome',
                onPressed: () => _recordOutcome(detail),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _applicationConsole(
    GatheringDetailPresentationSlice detail,
    GatheringPrivateDetailSlice private,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          widget.copy.applicationsTitle,
          style: TextStyle(
            color: _primaryTextColor,
            fontSize: AppTypography.base,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        ...private.applications.map(
          (application) => Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  application.displayName,
                  style: TextStyle(
                    color: _primaryTextColor,
                    fontSize: AppTypography.base,
                  ),
                ),
                if (application.answers.isNotEmpty)
                  Text(
                    application.answers
                        .map((answer) => answer.answerText)
                        .where((answer) => answer.trim().isNotEmpty)
                        .join('\n'),
                    semanticsLabel: widget.copy.applicationAnswersLabel,
                    style: TextStyle(
                      color: _secondaryTextColor,
                      fontSize: AppTypography.sm,
                    ),
                  ),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: _consoleButton(
                        key: GatheringDetailPage.approveKey(
                          application.personaId,
                        ),
                        label: widget.copy.approveAction,
                        actionId: 'approve-${application.personaId}',
                        onPressed: () => _reviewApplication(
                          detail,
                          application,
                          GatheringApplicationDecision.approve,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Expanded(
                      child: _consoleButton(
                        key: GatheringDetailPage.rejectKey(
                          application.personaId,
                        ),
                        label: widget.copy.rejectAction,
                        actionId: 'reject-${application.personaId}',
                        onPressed: () => _reviewApplication(
                          detail,
                          application,
                          GatheringApplicationDecision.reject,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _inviteConsole(GatheringDetailPresentationSlice detail) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        GatheringLabeledTextField(
          label: widget.copy.personaIdLabel,
          controller: _invitePersonaController,
          placeholder: widget.copy.personaIdLabel,
        ),
        _consoleButton(
          key: const ValueKey<String>('gathering-invite'),
          label: widget.copy.inviteAction,
          actionId: 'invite',
          onPressed: () => _invite(detail),
        ),
      ],
    );
  }

  Widget _rosterConsole(
    GatheringDetailPresentationSlice detail,
    GatheringPrivateDetailSlice private,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          widget.copy.rosterTitle,
          style: TextStyle(
            color: _primaryTextColor,
            fontSize: AppTypography.base,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        ...private.roster.map(
          (member) => Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  member.displayName,
                  style: TextStyle(
                    color: _primaryTextColor,
                    fontSize: AppTypography.base,
                  ),
                ),
              ),
              CupertinoButton(
                key: GatheringDetailPage.removeKey(member.personaId),
                onPressed: _busyActions.contains('remove-${member.personaId}')
                    ? null
                    : () => unawaited(_remove(detail, member)),
                child: Text(widget.copy.removeAction),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _consoleButton({
    required Key key,
    required String label,
    required String actionId,
    required VoidCallback onPressed,
  }) {
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: Semantics(
        button: true,
        label: label,
        child: CupertinoButton(
          key: key,
          color: AppColors.primaryColor,
          minimumSize: const Size(
            AppSpacing.minInteractiveSize,
            AppSpacing.minInteractiveSize,
          ),
          onPressed: _busyActions.contains(actionId) ? null : onPressed,
          child: _busyActions.contains(actionId)
              ? AppRequestFeedback.inline(indicatorColor: CupertinoColors.white)
              : Text(label),
        ),
      ),
    );
  }

  Future<void> _reviewApplication(
    GatheringDetailPresentationSlice detail,
    GatheringApplicationInboxItemSlice application,
    GatheringApplicationDecision decision,
  ) {
    final action = decision == GatheringApplicationDecision.approve
        ? 'approve-${application.personaId}'
        : 'reject-${application.personaId}';
    return _runAction(
      action,
      (writer, value) => writer.reviewApplication(
        GatheringReviewApplicationInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            action,
            application.personaId,
          ),
          gatheringId: detail.publicDetail.gatheringId,
          participantPersonaId: application.personaId,
          decision: decision,
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
          expectedParticipationVersion: application.participationVersion,
          reasonRef: _reasonController.text.trim(),
        ),
      ),
    );
  }

  Future<void> _invite(GatheringDetailPresentationSlice detail) {
    final personaId = _invitePersonaController.text.trim();
    if (personaId.isEmpty) return Future<void>.value();
    return _runAction(
      'invite',
      (writer, value) => writer.invite(
        GatheringInviteInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            'invite',
            personaId,
          ),
          gatheringId: detail.publicDetail.gatheringId,
          participantPersonaId: personaId,
          seatHoldUntil: DateTime.now().add(const Duration(days: 1)),
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
          expectedParticipationVersion: 0,
        ),
      ),
    );
  }

  Future<void> _remove(
    GatheringDetailPresentationSlice detail,
    GatheringRosterItemSlice member,
  ) {
    return _runAction(
      'remove-${member.personaId}',
      (writer, value) => writer.removeParticipant(
        GatheringRemoveParticipantInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            'remove',
            member.personaId,
          ),
          gatheringId: detail.publicDetail.gatheringId,
          participantPersonaId: member.personaId,
          reasonRef: _reasonController.text.trim(),
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
          expectedParticipationVersion: member.participationVersion,
        ),
      ),
    );
  }

  Future<void> _changeCapacity(GatheringDetailPresentationSlice detail) {
    final capacity = int.tryParse(_capacityController.text.trim());
    if (capacity == null || capacity <= 0) return Future<void>.value();
    return _runAction(
      'change-capacity',
      (writer, value) => writer.changeCapacity(
        GatheringChangeCapacityInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            'change-capacity',
          ),
          gatheringId: detail.publicDetail.gatheringId,
          maxParticipants: capacity,
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
        ),
      ),
    );
  }

  Future<void> _changeAdmission(
    GatheringDetailPresentationSlice detail,
    GatheringPrivateDetailSlice private,
  ) {
    return _runAction(
      'change-admission',
      (writer, value) => writer.changeAdmission(
        GatheringChangeAdmissionInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            'change-admission',
          ),
          gatheringId: detail.publicDetail.gatheringId,
          action: private.admissionPaused
              ? GatheringAdmissionControlAction.resume
              : GatheringAdmissionControlAction.pause,
          reasonRef: _reasonController.text.trim(),
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
          expectedAdmissionControlVersion: private.admissionControlVersion,
        ),
      ),
    );
  }

  Future<void> _materialUpdate(
    GatheringDetailPresentationSlice detail,
    GatheringPrivateDetailSlice private,
  ) {
    return _runAction(
      'material-update',
      (writer, value) => writer.update(
        GatheringUpdateInput(
          idempotencyKey: _idempotencyKey(
            detail.publicDetail,
            'material-update',
          ),
          gatheringId: detail.publicDetail.gatheringId,
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
          host: private.host,
          purpose: private.purpose,
          schedule: private.schedule,
          place: private.place,
          policy: private.policy,
        ),
      ),
    );
  }

  Future<void> _cancel(GatheringDetailPresentationSlice detail) {
    return _runAction(
      'cancel',
      (writer, value) => writer.cancel(
        GatheringReasonCommandInput(
          idempotencyKey: _idempotencyKey(detail.publicDetail, 'cancel'),
          gatheringId: detail.publicDetail.gatheringId,
          reasonRef: _reasonController.text.trim(),
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
        ),
      ),
    );
  }

  Future<void> _start(GatheringDetailPresentationSlice detail) {
    return _runAction(
      'start',
      (writer, value) => writer.start(
        GatheringVersionCommandInput(
          idempotencyKey: _idempotencyKey(detail.publicDetail, 'start'),
          gatheringId: detail.publicDetail.gatheringId,
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
        ),
      ),
    );
  }

  Future<void> _recordOutcome(GatheringDetailPresentationSlice detail) {
    return _runAction(
      'outcome',
      (writer, value) => writer.recordOutcome(
        GatheringOutcomeCommandInput(
          idempotencyKey: _idempotencyKey(detail.publicDetail, 'outcome'),
          gatheringId: detail.publicDetail.gatheringId,
          status: _selectedOutcome,
          expectedGatheringVersion: detail.publicDetail.aggregateVersion,
        ),
      ),
    );
  }
}
