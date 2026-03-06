import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';

class AssistantChatSettingsPage extends ConsumerStatefulWidget {
  const AssistantChatSettingsPage({
    super.key,
    required this.currentSessionId,
    required this.currentTopicTitle,
    required this.onOpenTrace,
    required this.onSessionSelected,
  });

  final String currentSessionId;
  final String currentTopicTitle;
  final VoidCallback onOpenTrace;
  final Future<void> Function(String sessionId) onSessionSelected;

  @override
  ConsumerState<AssistantChatSettingsPage> createState() =>
      _AssistantChatSettingsPageState();
}

class _AssistantChatSettingsPageState
    extends ConsumerState<AssistantChatSettingsPage> {
  late String _topicTitle;

  @override
  void initState() {
    super.initState();
    _topicTitle = widget.currentTopicTitle.trim().isEmpty
        ? UITextConstants.assistantHistoryAll
        : widget.currentTopicTitle;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockBg = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final gateway = ref.read(assistantGatewayProvider);
    final currentModel = gateway.currentModel() ?? '';
    final modelText = currentModel.trim().isEmpty
        ? UITextConstants.assistantModelSelectorEmpty
        : _shortModelName(currentModel);

    return CupertinoPageScaffold(
      backgroundColor: pageBg,
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          UITextConstants.settings,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: Icon(CupertinoIcons.back, color: fgPrimary),
        ),
      ),
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          children: [
            Container(
              decoration: BoxDecoration(
                color: blockBg,
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.blockBorderRadius,
                ),
                border: Border.all(
                  color: SettingsSemanticConstants.blockBorderColor(isDark),
                ),
              ),
              child: Column(
                children: [
                  _SettingsEntryRow(
                    title: UITextConstants.assistantSettingsModel,
                    value: modelText,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                    onTap: _openModelSelector,
                  ),
                  _divider(isDark),
                  if (kDebugMode) ...[
                    _SettingsEntryRow(
                      title: UITextConstants.assistantSettingsTraceSession,
                      value: '',
                      fgPrimary: fgPrimary,
                      fgSecondary: fgSecondary,
                      onTap: widget.onOpenTrace,
                    ),
                    _divider(isDark),
                  ],
                  _SettingsEntryRow(
                    title: UITextConstants.assistantSettingsConversationHistory,
                    value: _topicTitle,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                    onTap: _openHistoryPage,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _divider(bool isDark) {
    return Container(
      height: SettingsSemanticConstants.dividerThickness,
      color: SettingsSemanticConstants.dividerColor(isDark),
    );
  }

  String _shortModelName(String modelRef) {
    final slash = modelRef.indexOf('/');
    if (slash < 0 || slash >= modelRef.length - 1) return modelRef;
    return modelRef.substring(slash + 1);
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
    final selected = await showCupertinoModalPopup<String>(
      context: context,
      builder: (sheetContext) {
        final current = gateway.currentModel();
        return CupertinoActionSheet(
          title: Text(UITextConstants.assistantModelSelectorTitle),
          message: Text(UITextConstants.assistantModelSelectorHint),
          actions: models
              .map(
                (modelRef) => CupertinoActionSheetAction(
                  onPressed: () => Navigator.of(sheetContext).pop(modelRef),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(_shortModelName(modelRef)),
                      if (modelRef == current) ...[
                        SizedBox(width: AppSpacing.xs),
                        Icon(
                          CupertinoIcons.check_mark,
                          size: AppSpacing.iconSmall,
                        ),
                      ],
                    ],
                  ),
                ),
              )
              .toList(growable: false),
          cancelButton: CupertinoActionSheetAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(sheetContext).pop(),
            child: Text(UITextConstants.cancel),
          ),
        );
      },
    );
    if (selected == null || selected.trim().isEmpty) return;
    final switched = gateway.switchModel(selected);
    if (!switched || !mounted) return;
    setState(() {});
  }

  Future<void> _openHistoryPage() async {
    final selected = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _AssistantConversationHistoryPage(
          currentSessionId: widget.currentSessionId,
        ),
      ),
    );
    if (selected == null || selected.isEmpty) return;
    await widget.onSessionSelected(selected);
    if (!mounted) return;
    final sessions = await ref.read(assistantGatewayProvider).listSessions();
    if (!mounted) return;
    for (final item in sessions) {
      if ((item['sessionId'] ?? '').toString() != selected) continue;
      setState(() {
        _topicTitle =
            (item['topicTitle'] as String?)?.trim().isNotEmpty == true
            ? (item['topicTitle'] as String).trim()
            : UITextConstants.assistantHistoryAll;
      });
      break;
    }
  }
}

class _AssistantConversationHistoryPage extends ConsumerWidget {
  const _AssistantConversationHistoryPage({
    required this.currentSessionId,
  });

  final String currentSessionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    return CupertinoPageScaffold(
      backgroundColor: pageBg,
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          UITextConstants.assistantSettingsConversationHistory,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: Icon(CupertinoIcons.back, color: fgPrimary),
        ),
      ),
      child: SafeArea(
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: ref.read(assistantGatewayProvider).listSessions(),
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Center(child: CupertinoActivityIndicator());
            }
            final sessions = snapshot.data ?? const <Map<String, dynamic>>[];
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
                final sessionId = (item['sessionId'] ?? '').toString();
                final title = (item['topicTitle'] ?? '').toString().trim();
                final summary = (item['topicSummary'] ?? '').toString().trim();
                final count = (item['messageCount'] as int?) ?? 0;
                final subtitle = summary.isNotEmpty
                    ? summary
                    : UITextConstants.assistantHistoryMessageCount.replaceFirst(
                        '%s',
                        count.toString(),
                      );
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
  final VoidCallback onTap;

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
              style: TextStyle(
                fontSize: AppTypography.base,
                color: fgPrimary,
              ),
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
                      color: CupertinoColors.secondaryLabel.resolveFrom(context),
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
