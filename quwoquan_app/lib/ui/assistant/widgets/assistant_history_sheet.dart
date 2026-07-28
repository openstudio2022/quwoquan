import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/conversation_sheet.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

/// 历史会话抽屉（surface `assistantHistory`：私助记录抽屉与分页）。
///
/// 数据源唯一：`ListAssistantConversations` keyset 分页（R-ASSIST-001 收口，
/// 本地不再维护会话副本）。返回选中的 conversationId；返回空串表示新对话。
Future<String?> showAssistantHistorySheet(BuildContext context) {
  return showAppBottomModal<String>(
    context: context,
    builder: (modalContext) => const _AssistantHistorySheet(),
  );
}

class _AssistantHistorySheet extends ConsumerStatefulWidget {
  const _AssistantHistorySheet();

  @override
  ConsumerState<_AssistantHistorySheet> createState() =>
      _AssistantHistorySheetState();
}

class _AssistantHistorySheetState
    extends ConsumerState<_AssistantHistorySheet> {
  final List<AssistantConversationWire> _conversations =
      <AssistantConversationWire>[];
  String _nextCursor = '';
  bool _loading = true;
  bool _loadingMore = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFirstPage());
  }

  Future<void> _loadFirstPage() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ref
          .read(assistantConversationRunFacetProvider)
          .listAssistantConversations();
      if (!mounted) return;
      setState(() {
        _conversations
          ..clear()
          ..addAll(page.items);
        _nextCursor = page.nextCursor;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _nextCursor.isEmpty) return;
    setState(() => _loadingMore = true);
    try {
      final page = await ref
          .read(assistantConversationRunFacetProvider)
          .listAssistantConversations(cursor: _nextCursor);
      if (!mounted) return;
      setState(() {
        _conversations.addAll(page.items);
        _nextCursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (_) {
      // 分页加载失败保留既有列表；用户可重新点击加载更多。
      if (!mounted) return;
      setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final l10n = context.l10n;
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ConversationSheetHeader(
            isDark: isDark,
            title: AssistantText.assistantHistoryTitle,
          ),
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            ),
            child: ConversationSheetPrimaryActionButton(
              isDark: isDark,
              label: AssistantText.assistantNewConversation,
              onTap: () => Navigator.of(context).pop(''),
            ),
          ),
          SizedBox(
            height: SettingsSemanticConstants.conversationSheetSectionGap,
          ),
          Flexible(child: _buildBody(isDark, l10n)),
        ],
      ),
    );
  }

  Widget _buildBody(bool isDark, AppLocalizations l10n) {
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    if (_loading) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.lg),
        child: AppRequestFeedback.section(),
      );
    }
    final error = _error;
    if (error != null) {
      return AppSectionErrorCard(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.section,
          presentation: UiErrorPresentation.sectionSoftCard,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadFirstPage();
          }
        },
      );
    }
    if (_conversations.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.lg),
        child: Text(
          AssistantText.assistantHistoryEmpty,
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: AppTypography.sm, color: secondary),
        ),
      );
    }
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: SettingsSemanticConstants.blockHorizontalPadding,
      ),
      child: ConversationSheetListCard(
        isDark: isDark,
        child: ListView.separated(
          shrinkWrap: true,
          itemCount: _conversations.length + (_nextCursor.isNotEmpty ? 1 : 0),
          separatorBuilder: (_, _) => ConversationSheetDivider(
            isDark: isDark,
            dividerLeftInset: SettingsSemanticConstants.blockHorizontalPadding,
          ),
          itemBuilder: (context, index) {
            if (index == _conversations.length) {
              return CupertinoButton(
                key: const ValueKey<String>('assistant_history_load_more'),
                minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                onPressed: _loadMore,
                child: _loadingMore
                    ? AppRequestFeedback.inline()
                    : Text(
                        l10n.seeMore,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: secondary,
                        ),
                      ),
              );
            }
            final conversation = _conversations[index];
            return _conversationRow(isDark, conversation);
          },
        ),
      ),
    );
  }

  Widget _conversationRow(bool isDark, AssistantConversationWire conversation) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    final title = conversation.summary.trim().isEmpty
        ? AssistantText.assistantHistoryDefaultTitle
        : conversation.summary.trim();
    final updatedLabel = _relativeUpdatedLabel(conversation.updatedAt);
    return CupertinoButton(
      key: ValueKey<String>(
        'assistant_history_item_${conversation.conversationId}',
      ),
      padding: EdgeInsets.symmetric(
        horizontal: SettingsSemanticConstants.blockHorizontalPadding,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: () => Navigator.of(context).pop(conversation.conversationId),
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
                    color: primary,
                  ),
                ),
                if (updatedLabel.isNotEmpty)
                  Text(
                    updatedLabel,
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: secondary,
                    ),
                  ),
              ],
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconSmall,
            color: secondary,
          ),
        ],
      ),
    );
  }

  String _relativeUpdatedLabel(String updatedAt) {
    final parsed = DateTime.tryParse(updatedAt.trim());
    if (parsed == null) {
      return '';
    }
    final l10n = context.l10n;
    final local = parsed.toLocal();
    final delta = DateTime.now().difference(local);
    if (delta.inMinutes < 1) return l10n.justNow;
    if (delta.inMinutes < 60) return l10n.minutesAgoTemplate(delta.inMinutes);
    if (delta.inHours < 24) return l10n.hoursAgoTemplate(delta.inHours);
    if (delta.inDays < 30) return l10n.daysAgoTemplate(delta.inDays);
    return l10n.monthDayTemplate(local.month, local.day);
  }
}
