import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_widgets.dart';

class ForwardRecipientPickerRoute extends ConsumerStatefulWidget {
  const ForwardRecipientPickerRoute({super.key, required this.payload});

  final AppForwardPayload payload;

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
    final repo = ref.read(chatRepositoryProvider);
    final conversations = await repo.listConversations(limit: 50);
    final contacts = await repo.listContactHome(filter: 'all', limit: 500);
    final recent = uniqueForwardRecipients(
      sortForwardRecipientsByRecent(
        conversations.map(AppForwardRecipient.fromConversation),
      ),
    );
    final contactRecipients = contacts
        .where((row) => row.kind.trim().toLowerCase() != 'circle')
        .map(AppForwardRecipient.fromContactHome);
    return _ForwardPickerData(
      recent: recent,
      contacts: uniqueForwardRecipients(
        sortForwardRecipientsByRecent(contactRecipients),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: UITextConstants.forwardSelectChatTitle,
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
              placeholder: UITextConstants.search,
              elevated: false,
              onChanged: (value) => setState(() => _query = value.trim()),
            ),
          ),
          Expanded(
            child: FutureBuilder<_ForwardPickerData>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CupertinoActivityIndicator());
                }
                if (snapshot.hasError) {
                  return _ForwardPickerErrorState(
                    semantic: runtimeErrorSemantic(
                      context,
                      error:
                          snapshot.error ??
                          StateError(UITextConstants.forwardCardUnavailable),
                      category: UiErrorCategory.sectionLoad,
                      scope: UiErrorScope.section,
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
      return _ForwardPickerEmptyState(isDark: isDark);
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
            title: UITextConstants.forwardRecentChats,
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
          ForwardSectionHeader(
            isDark: isDark,
            title: UITextConstants.forwardContacts,
          ),
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

class _ForwardPickerEmptyState extends StatelessWidget {
  const _ForwardPickerEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Text(
          UITextConstants.forwardNoRecipients,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color:
                SettingsSemanticConstants.conversationSheetSecondaryLabelColor(
                  isDark,
                ),
          ),
        ),
      ),
    );
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
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: AppSectionErrorCard(
          semantic: semantic,
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              onRetry();
            }
          },
        ),
      ),
    );
  }
}
