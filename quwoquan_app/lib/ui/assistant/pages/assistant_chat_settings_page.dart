import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_gateway_ui_views.dart';

class AssistantChatSettingsPage extends ConsumerStatefulWidget {
  const AssistantChatSettingsPage({
    super.key,
    required this.currentSessionId,
    required this.currentTopicTitle,
    required this.currentBackend,
    required this.onOpenTrace,
    required this.onSessionSelected,
    required this.onBackendSelected,
  });

  final String currentSessionId;
  final String currentTopicTitle;
  final AssistantBackend currentBackend;
  final VoidCallback onOpenTrace;
  final Future<void> Function(String sessionId) onSessionSelected;
  final Future<String> Function(AssistantBackend backend) onBackendSelected;

  @override
  ConsumerState<AssistantChatSettingsPage> createState() =>
      _AssistantChatSettingsPageState();
}

class _AssistantChatSettingsPageState
    extends ConsumerState<AssistantChatSettingsPage> {
  late String _topicTitle;
  late AssistantBackend _backend;
  late String _sessionId;

  @override
  void initState() {
    super.initState();
    _backend = widget.currentBackend;
    _sessionId = widget.currentSessionId;
    _topicTitle = widget.currentTopicTitle.trim().isEmpty
        ? UITextConstants.assistantHistoryAll
        : widget.currentTopicTitle;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final gateway = ref.read(assistantGatewayProvider);
    final currentModel = gateway.currentModel() ?? '';
    final modelText = currentModel.trim().isEmpty
        ? UITextConstants.assistantModelSelectorEmpty
        : _shortModelName(currentModel);

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settings,
      onBack: () => Navigator.of(context).pop(),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.only(
            left: SettingsSemanticConstants.insetFormListHorizontalPadding,
            right: SettingsSemanticConstants.insetFormListHorizontalPadding,
            top: AppSpacing.intraGroupSm,
            bottom: AppSpacing.xl,
          ),
          children: [
            SettingsInsetGroupedSection(
              isDark: isDark,
              child: Column(
                children: [
                  _SettingsEntryRow(
                    title: UITextConstants.assistantSettingsBackend,
                    value: _backendLabel(_backend),
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                    onTap: _openBackendSelector,
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  _SettingsEntryRow(
                    title: UITextConstants.assistantSettingsModel,
                    value: _backend == AssistantBackend.local
                        ? modelText
                        : UITextConstants.assistantBackendRemote,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                    onTap: _backend == AssistantBackend.local
                        ? _openModelSelector
                        : null,
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  if (kDebugMode) ...[
                    _SettingsEntryRow(
                      title: UITextConstants.assistantSettingsTraceSession,
                      value: '',
                      fgPrimary: fgPrimary,
                      fgSecondary: fgSecondary,
                      onTap: widget.onOpenTrace,
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                  ],
                  _SettingsEntryRow(
                    title: UITextConstants.assistantSettingsConversationHistory,
                    value: _backend == AssistantBackend.local
                        ? _topicTitle
                        : UITextConstants
                              .assistantSettingsRemoteHistoryDisabled,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                    onTap: _backend == AssistantBackend.local
                        ? _openHistoryPage
                        : null,
                  ),
                ],
              ),
            ),
            if (_backend == AssistantBackend.local) ...[
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              _PreferenceFactsSection(currentSessionId: _sessionId),
            ],
          ],
        ),
      ),
    );
  }

  String _shortModelName(String modelRef) {
    final slash = modelRef.indexOf('/');
    if (slash < 0 || slash >= modelRef.length - 1) return modelRef;
    return modelRef.substring(slash + 1);
  }

  String _backendLabel(AssistantBackend backend) {
    switch (backend) {
      case AssistantBackend.local:
        return UITextConstants.assistantBackendLocal;
      case AssistantBackend.remote:
        return UITextConstants.assistantBackendRemote;
    }
  }

  Future<void> _openBackendSelector() async {
    final remoteConfigured = ref.read(assistantRemoteConfiguredProvider);
    final availableBackends = remoteConfigured
        ? AssistantBackend.values
        : const <AssistantBackend>[AssistantBackend.local];
    final selected = await showAppActionSheet<AssistantBackend>(
      context,
      title: UITextConstants.assistantSettingsBackend,
      message: UITextConstants.assistantSettingsBackendHint,
      sections: [
        AppActionSheetSection<AssistantBackend>(
          items: availableBackends
              .map(
                (backend) => AppActionSheetItem<AssistantBackend>(
                  value: backend,
                  label: _backendLabel(backend),
                  isSelected: backend == _backend,
                ),
              )
              .toList(growable: false),
        ),
      ],
    );
    if (selected == null || selected == _backend) return;
    final nextSessionId = await widget.onBackendSelected(selected);
    if (!mounted) return;
    setState(() {
      _backend = selected;
      _sessionId = nextSessionId;
      _topicTitle = UITextConstants.assistantHistoryAll;
    });
  }

  Future<void> _openModelSelector() async {
    final gateway = ref.read(assistantGatewayProvider);
    final models = gateway.listAvailableModels();
    if (models.isEmpty) {
      if (!mounted) return;
      await showCupertinoDialog<void>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: Text(UITextConstants.assistantModelSelectorTitle),
          content: Text(UITextConstants.assistantModelUnavailable),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(UITextConstants.confirm),
            ),
          ],
        ),
      );
      return;
    }
    final current = gateway.currentModel();
    final selected = await showAppActionSheet<String>(
      context,
      title: UITextConstants.assistantModelSelectorTitle,
      message: UITextConstants.assistantModelSelectorHint,
      sections: [
        AppActionSheetSection<String>(
          items: models
              .map(
                (modelRef) => AppActionSheetItem<String>(
                  value: modelRef,
                  label: _shortModelName(modelRef),
                  isSelected: modelRef == current,
                ),
              )
              .toList(growable: false),
        ),
      ],
    );
    if (selected == null || selected.trim().isEmpty) return;
    final switched = gateway.switchModel(selected);
    if (!switched || !mounted) return;
    setState(() {});
  }

  Future<void> _openHistoryPage() async {
    final selected = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.assistantChatSettingsHistory,
        ),
        builder: (_) =>
            _AssistantConversationHistoryPage(currentSessionId: _sessionId),
      ),
    );
    if (selected == null || selected.isEmpty) return;
    await widget.onSessionSelected(selected);
    if (!mounted) return;
    final sessions = await ref.read(assistantGatewayProvider).listSessions();
    if (!mounted) return;
    for (final d in sessions) {
      if (d.sessionId != selected) continue;
      setState(() {
        _sessionId = selected;
        final t = d.topicTitle.trim();
        _topicTitle = t.isNotEmpty ? t : UITextConstants.assistantHistoryAll;
      });
      break;
    }
  }
}

class _PreferenceFactsSection extends ConsumerWidget {
  const _PreferenceFactsSection({required this.currentSessionId});

  final String currentSessionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    return FutureBuilder<AssistantSessionDetailView>(
      future: ref
          .read(assistantGatewayProvider)
          .sessionDetail(currentSessionId)
          .then(
            (detail) => detail == null
                ? const AssistantSessionDetailView(
                    sessionPreferenceFacts: <AssistantPreferenceFactView>[],
                    longTermPreferenceFacts: <AssistantPreferenceFactView>[],
                  )
                : AssistantSessionDetailView.fromWire(detail),
          ),
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return SettingsInsetGroupedSection(
            isDark: isDark,
            header: '偏好事实',
            child: const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CupertinoActivityIndicator()),
            ),
          );
        }
        final detail = snapshot.data!;
        final sessionFacts = detail.sessionPreferenceFacts;
        final longTermFacts = detail.longTermPreferenceFacts;
        return SettingsInsetGroupedSection(
          isDark: isDark,
          header: '偏好事实',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '当前会话即时生效，长期事实会随记录积累展示在这里。',
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
              SizedBox(height: AppSpacing.containerMd),
              _PreferenceFactList(
                title: '本会话',
                facts: sessionFacts,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
              ),
              SizedBox(height: AppSpacing.containerSm),
              _PreferenceFactList(
                title: '长期',
                facts: longTermFacts,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PreferenceFactList extends StatelessWidget {
  const _PreferenceFactList({
    required this.title,
    required this.facts,
    required this.fgPrimary,
    required this.fgSecondary,
  });

  final String title;
  final List<AssistantPreferenceFactView> facts;
  final Color fgPrimary;
  final Color fgSecondary;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.md,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        SizedBox(height: AppSpacing.xs),
        if (facts.isEmpty)
          Text(
            '暂无记录',
            style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
          ),
        for (final fact in facts.take(6))
          Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.xs),
            child: Text(
              '• ${fact.keyText}：${fact.valueText}',
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            ),
          ),
      ],
    );
  }
}

class _AssistantConversationHistoryPage extends ConsumerWidget {
  const _AssistantConversationHistoryPage({required this.currentSessionId});

  final String currentSessionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SettingsSemanticConstants.pageChromeOverlayStyle(isDark),
      child: AppScaffold(
        backgroundColor: pageBg,
        navigationBar: AppNavigationBar(
          middle: Text(
            UITextConstants.assistantSettingsConversationHistory,
            style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
          ),
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () => Navigator.of(context).pop(),
          ),
        ),
        child: SafeArea(
          child: FutureBuilder<List<AssistantLocalSessionSummaryView>>(
            future: ref
                .read(assistantGatewayProvider)
                .listSessions()
                .then(
                  (raw) => raw
                      .map(AssistantLocalSessionSummaryView.fromDescriptor)
                      .where(
                        (item) => isAssistantSessionForBackend(
                          item.sessionId,
                          AssistantBackend.local,
                        ),
                      )
                      .toList(growable: false),
                ),
            builder: (context, snapshot) {
              if (!snapshot.hasData) {
                return const Center(child: CupertinoActivityIndicator());
              }
              final sessions = snapshot.data ?? const [];
              if (sessions.isEmpty) {
                return Center(
                  child: Text(
                    UITextConstants.assistantHistoryEmpty,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: fgSecondary,
                    ),
                  ),
                );
              }
              return ListView.separated(
                padding: EdgeInsets.all(AppSpacing.containerMd),
                itemCount: sessions.length + 1,
                separatorBuilder: (context, index) =>
                    SizedBox(height: AppSpacing.xs),
                itemBuilder: (context, index) {
                  if (index == 0) {
                    return _SessionTile(
                      title: UITextConstants.assistantHistoryAll,
                      subtitle: UITextConstants.assistantHistoryAllSubtitle
                          .replaceFirst('%s', sessions.length.toString()),
                      selected: false,
                      onTap: () => Navigator.of(context).pop(currentSessionId),
                    );
                  }
                  final item = sessions[index - 1];
                  final sessionId = item.sessionId;
                  final title = item.topicTitle.trim();
                  final summary = item.topicSummary.trim();
                  final count = item.messageCount;
                  final subtitle = summary.isNotEmpty
                      ? summary
                      : UITextConstants.assistantHistoryMessageCount
                            .replaceFirst('%s', count.toString());
                  return _SessionTile(
                    title: title.isEmpty
                        ? UITextConstants.assistantHistoryUntitled
                        : title,
                    subtitle: subtitle,
                    selected: sessionId == currentSessionId,
                    onTap: () => Navigator.of(context).pop(sessionId),
                  );
                },
              );
            },
          ),
        ),
      ),
    );
  }
}

class _SettingsEntryRow extends StatelessWidget {
  const _SettingsEntryRow({
    required this.title,
    required this.value,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.onTap,
  });

  final String title;
  final String value;
  final Color fgPrimary;
  final Color fgSecondary;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: SettingsSemanticConstants.blockHorizontalPadding,
        vertical: SettingsSemanticConstants.sectionVerticalPadding,
      ),
      onPressed: onTap,
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: TextStyle(fontSize: AppTypography.base, color: fgPrimary),
            ),
          ),
          if (value.trim().isNotEmpty)
            Flexible(
              child: Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          SizedBox(width: AppSpacing.xs),
          if (onTap != null)
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: fgSecondary,
            ),
        ],
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: CupertinoColors.systemBackground.resolveFrom(context),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: CupertinoButton(
        pressedOpacity: 0.6,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        onPressed: onTap,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.medium,
                      color: CupertinoColors.label.resolveFrom(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs / 2),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: CupertinoColors.secondaryLabel.resolveFrom(
                        context,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (selected)
              Icon(
                CupertinoIcons.check_mark_circled_solid,
                size: AppSpacing.iconSmall,
                color: AppColors.primaryColor,
              ),
          ],
        ),
      ),
    );
  }
}
