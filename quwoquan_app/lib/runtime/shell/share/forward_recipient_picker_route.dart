import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/forward_share_dependencies.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_confirm_sheet.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_recipient_widgets.dart';

enum ForwardRecipientPickerMode { all, groups, messages }

class ForwardRecipientPickerRoute extends ConsumerStatefulWidget {
  const ForwardRecipientPickerRoute({
    super.key,
    required this.payload,
    this.mode = ForwardRecipientPickerMode.all,
  });

  final AppForwardPayload payload;
  final ForwardRecipientPickerMode mode;

  @override
  ConsumerState<ForwardRecipientPickerRoute> createState() =>
      _ForwardRecipientPickerRouteState();
}

class _ForwardRecipientPickerRouteState
    extends ConsumerState<ForwardRecipientPickerRoute> {
  late Future<_ForwardPickerData> _future;
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<_ForwardPickerData> _load() async {
    final dependencies = ref.read(forwardShareDependenciesProvider);
    final conversations = await dependencies.loadRecentRecipients(limit: 50);
    final contacts = await dependencies.loadContactRecipients(
      groupsOnly: widget.mode == ForwardRecipientPickerMode.groups,
      limit: 500,
    );
    final recent = uniqueForwardRecipients(
      sortForwardRecipientsByRecent(conversations.where(_matchesMode)),
    );
    final contactRecipients = contacts.where(_matchesMode);
    return _ForwardPickerData(
      recent: recent,
      contacts: uniqueForwardRecipients(
        sortForwardRecipientsByRecent(contactRecipients),
      ),
    );
  }

  bool _matchesMode(AppForwardRecipient recipient) {
    return switch (widget.mode) {
      ForwardRecipientPickerMode.all => true,
      ForwardRecipientPickerMode.groups =>
        recipient.kind == AppForwardRecipientKind.group,
      ForwardRecipientPickerMode.messages =>
        recipient.kind != AppForwardRecipientKind.group,
    };
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: switch (widget.mode) {
        ForwardRecipientPickerMode.all => ChatText.forwardSelectChatTitle,
        ForwardRecipientPickerMode.groups => ChatText.shareSelectGroupTitle,
        ForwardRecipientPickerMode.messages => ChatText.shareSelectMessageTitle,
      },
      onBack: () => Navigator.of(context).pop(false),
      body: Column(
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              SettingsSemanticConstants.blockHorizontalPadding,
              AppSpacing.containerMd,
              SettingsSemanticConstants.blockHorizontalPadding,
              AppSpacing.containerSm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: DiscoveryText.search,
              elevated: false,
              onChanged: (value) => setState(() => _query = value.trim()),
            ),
          ),
          Expanded(
            child: FutureBuilder<_ForwardPickerData>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return AppRequestFeedback.section();
                }
                if (snapshot.hasError) {
                  return _ForwardPickerErrorState(
                    semantic: ensureRetryUiErrorSemantic(
                      runtimeErrorSemantic(
                        context,
                        error:
                            snapshot.error ??
                            StateError(ChatText.forwardCardUnavailable),
                        category: UiErrorCategory.sectionLoad,
                        scope: UiErrorScope.section,
                      ),
                    ),
                    onRetry: () => setState(() => _future = _load()),
                  );
                }
                final data = snapshot.data ?? _ForwardPickerData.empty;
                return _ForwardPickerList(
                  isDark: isDark,
                  data: data,
                  query: _query,
                  onRecipientTap: _handleRecipientTap,
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _handleRecipientTap(AppForwardRecipient recipient) async {
    final sent = await ForwardConfirmSheet.show(
      context,
      payload: widget.payload,
      recipient: recipient,
    );
    if (sent == true && mounted) {
      Navigator.of(context).pop(true);
    }
  }
}

class _ForwardPickerData {
  const _ForwardPickerData({required this.recent, required this.contacts});

  static const empty = _ForwardPickerData(
    recent: <AppForwardRecipient>[],
    contacts: <AppForwardRecipient>[],
  );

  final List<AppForwardRecipient> recent;
  final List<AppForwardRecipient> contacts;
}

class _ForwardPickerList extends StatelessWidget {
  const _ForwardPickerList({
    required this.isDark,
    required this.data,
    required this.query,
    required this.onRecipientTap,
  });

  final bool isDark;
  final _ForwardPickerData data;
  final String query;
  final ValueChanged<AppForwardRecipient> onRecipientTap;

  @override
  Widget build(BuildContext context) {
    final normalizedQuery = query.trim().toLowerCase();
    final recent = _filter(data.recent, normalizedQuery);
    final contacts = _filter(data.contacts, normalizedQuery);
    if (recent.isEmpty && contacts.isEmpty) {
      return const AppEmptyState(title: ChatText.forwardNoRecipients);
    }
    return ListView(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.blockHorizontalPadding,
        AppSpacing.containerSm,
        SettingsSemanticConstants.blockHorizontalPadding,
        AppSpacing.containerXl,
      ),
      children: <Widget>[
        if (recent.isNotEmpty) ...<Widget>[
          ForwardSectionHeader(
            isDark: isDark,
            title: ChatText.forwardRecentChats,
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ForwardRecipientListCard(
            isDark: isDark,
            recipients: recent,
            onRecipientTap: onRecipientTap,
          ),
          SizedBox(height: AppSpacing.containerLg),
        ],
        if (contacts.isNotEmpty) ...<Widget>[
          ForwardSectionHeader(isDark: isDark, title: ChatText.forwardContacts),
          SizedBox(height: AppSpacing.intraGroupSm),
          ForwardRecipientListCard(
            isDark: isDark,
            recipients: contacts,
            onRecipientTap: onRecipientTap,
          ),
        ],
      ],
    );
  }

  List<AppForwardRecipient> _filter(
    List<AppForwardRecipient> recipients,
    String normalizedQuery,
  ) {
    if (normalizedQuery.isEmpty) {
      return recipients;
    }
    return recipients
        .where((recipient) {
          return recipient.title.toLowerCase().contains(normalizedQuery) ||
              recipient.displaySubtitle.toLowerCase().contains(normalizedQuery);
        })
        .toList(growable: false);
  }
}

class _ForwardPickerErrorState extends StatelessWidget {
  const _ForwardPickerErrorState({
    required this.semantic,
    required this.onRetry,
  });

  final UiErrorSemantic semantic;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppSectionErrorState(
      semantic: semantic,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          onRetry();
        }
      },
    );
  }
}
