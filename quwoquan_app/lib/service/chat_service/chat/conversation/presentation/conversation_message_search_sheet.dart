import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/formatters/chat_time_formatter.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/local_search_namespace.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_local_hit_views.dart';

/// 会话内「查找聊天记录」：本地全文索引 scoped 到当前会话，
/// 点击结果按搜索锚点语义进入会话定位（复用全局搜索同一跳转链）。
class ConversationMessageSearchSheet extends ConsumerStatefulWidget {
  const ConversationMessageSearchSheet({
    super.key,
    required this.conversationId,
  });

  final String conversationId;

  static Future<void> show(
    BuildContext context, {
    required String conversationId,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (_) =>
          ConversationMessageSearchSheet(conversationId: conversationId),
    );
  }

  @override
  ConsumerState<ConversationMessageSearchSheet> createState() =>
      _ConversationMessageSearchSheetState();
}

class _ConversationMessageSearchSheetState
    extends ConsumerState<ConversationMessageSearchSheet> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  List<MessageSearchItemView> _results = const <MessageSearchItemView>[];
  bool _searching = false;
  bool _hasQuery = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      unawaited(_search(value.trim()));
    });
  }

  Future<void> _search(String query) async {
    if (!mounted) return;
    setState(() {
      _hasQuery = query.isNotEmpty;
      _searching = query.isNotEmpty;
    });
    if (query.isEmpty) {
      setState(() => _results = const <MessageSearchItemView>[]);
      return;
    }
    try {
      final context = await ref.read(activePersonaContextProvider.future);
      final namespace = LocalSearchNamespace.fromActivePersonaContext(context);
      final results = await ref
          .read(localChatSearchStoreProvider)
          .searchMessages(
            namespace: namespace,
            query: query,
            conversationId: widget.conversationId,
            limit: 30,
          );
      if (!mounted) return;
      setState(() {
        _results = results;
        _searching = false;
      });
    } catch (_) {
      if (!mounted) return;
      // 本地索引查询失败按空结果呈现（索引缺失时无损降级），不阻断会话。
      setState(() {
        _results = const <MessageSearchItemView>[];
        _searching = false;
      });
    }
  }

  void _openResult(MessageSearchItemView item) {
    Navigator.of(context).pop();
    context.push(
      AppRoutePaths.chatDetail(id: item.conversationId),
      extra: SearchConversationAnchorContext(
        messageAnchorId: item.messageId,
        sourceQuery: _controller.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primary = SettingsSemanticConstants.conversationSheetPrimaryLabelColor(
      isDark,
    );
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: SettingsSemanticConstants.conversationSheetPanelBackground(
        isDark,
      ),
      contentPadding: EdgeInsets.all(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            ChatText.searchInConversationTitle,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: FontWeight.w600,
              color: primary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupLg),
          CupertinoSearchTextField(
            key: const ValueKey<String>('conversation_message_search_input'),
            controller: _controller,
            autofocus: true,
            placeholder: ChatText.searchInConversationPlaceholder,
            onChanged: _onQueryChanged,
          ),
          SizedBox(height: AppSpacing.intraGroupLg),
          Flexible(
            child: _hasQuery && !_searching && _results.isEmpty
                ? Padding(
                    padding: EdgeInsets.all(AppSpacing.containerMd),
                    child: Text(
                      ChatText.searchInConversationEmpty,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: primary.withValues(alpha: 0.6),
                      ),
                    ),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: _results.length,
                    itemBuilder: (context, index) {
                      final item = _results[index];
                      return CupertinoButton(
                        key: ValueKey<String>(
                          'conversation_search_result_${item.messageId}',
                        ),
                        padding: EdgeInsets.symmetric(
                          vertical: AppSpacing.intraGroupSm,
                          horizontal: AppSpacing.intraGroupXs,
                        ),
                        onPressed: () => _openResult(item),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    item.senderDisplayName?.trim().isNotEmpty ==
                                            true
                                        ? item.senderDisplayName!.trim()
                                        : item.conversationTitle?.trim() ?? '',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosFootnote,
                                      color: primary.withValues(alpha: 0.64),
                                    ),
                                  ),
                                  SizedBox(height: AppSpacing.xs),
                                  Text(
                                    item.highlightText?.trim().isNotEmpty ==
                                            true
                                        ? item.highlightText!.trim()
                                        : item.contentPreview,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosBody,
                                      color: primary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            SizedBox(width: AppSpacing.intraGroupSm),
                            Text(
                              ChatTimeFormatter.format(item.timestamp),
                              style: TextStyle(
                                fontSize: AppTypography.caption,
                                color: primary.withValues(alpha: 0.5),
                              ),
                            ),
                            SizedBox(width: AppSpacing.intraGroupXs),
                            Icon(
                              CupertinoIcons.chevron_forward,
                              size: AppSpacing.iconSmall,
                              color: AppColors.primaryColor.withValues(
                                alpha: 0.7,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
