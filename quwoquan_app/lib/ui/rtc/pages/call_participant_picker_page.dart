import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/rtc/models/call_picker_participant_row.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

enum _ParticipantSource { currentConversation, sameInterest, otherGroups }

class CallParticipantPickerPage extends ConsumerStatefulWidget {
  const CallParticipantPickerPage({super.key, required this.routeExtra});

  final CallParticipantPickerRouteExtra routeExtra;

  String? get callId => routeExtra.callId;
  String? get conversationId => routeExtra.conversationId;
  bool get defaultSelectAll => routeExtra.defaultSelectAll;
  int get selectionLimit => routeExtra.selectionLimit;
  bool get allowsCrossContextSources => routeExtra.allowsCrossContextSources;

  @override
  ConsumerState<CallParticipantPickerPage> createState() =>
      _CallParticipantPickerPageState();
}

class _CallParticipantPickerPageState
    extends ConsumerState<CallParticipantPickerPage> {
  final Set<String> _selectedIds = {};
  String _searchQuery = '';
  List<CallPickerParticipantRow> _contacts = [];
  List<ChatInboxViewData> _availableGroups = [];
  bool _isLoading = true;
  UiErrorSemantic? _pageErrorSemantic;
  _ParticipantSource _source = _ParticipantSource.currentConversation;
  String? _selectedGroupId;

  @override
  void initState() {
    super.initState();
    _loadContacts();
  }

  Future<void> _loadContacts() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _pageErrorSemantic = null;
      });
    }
    try {
      final contacts = await _loadContactsForSource(_source);
      final groups = widget.allowsCrossContextSources
          ? await _loadAvailableGroups()
          : const <ChatInboxViewData>[];
      if (mounted) {
        setState(() {
          _contacts = contacts;
          _availableGroups = groups;
          if (_selectedGroupId == null && groups.isNotEmpty) {
            _selectedGroupId = groups.first.id;
          }
          _isLoading = false;
          _pageErrorSemantic = null;
          _applyDefaultSelectionIfNeeded(contacts);
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _pageErrorSemantic = runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          );
        });
      }
    }
  }

  Future<List<ChatInboxViewData>> _loadAvailableGroups() async {
    if (!widget.allowsCrossContextSources) {
      return const <ChatInboxViewData>[];
    }
    final inbox = await ref
        .read(chatConversationRepositoryProvider)
        .listInbox(limit: 100);
    final currentConversationId = widget.conversationId;
    return inbox
        .where((item) {
          return item.type == 'group' &&
              item.id.isNotEmpty &&
              item.id != currentConversationId;
        })
        .toList(growable: false);
  }

  Future<List<CallPickerParticipantRow>> _loadContactsForSource(
    _ParticipantSource source,
  ) async {
    final contactRepo = ref.read(chatContactRepositoryProvider);
    final memberRepo = ref.read(chatMemberRepositoryProvider);
    final currentUserId = ref.read(userDataProvider)?.id ?? '';
    switch (source) {
      case _ParticipantSource.currentConversation:
        final convId = widget.conversationId;
        if (convId == null || convId.isEmpty) {
          if (!widget.allowsCrossContextSources) {
            return const <CallPickerParticipantRow>[];
          }
          final page = await contactRepo.listContacts(limit: 100);
          return page.items
              .map(CallPickerParticipantRow.fromContact)
              .toList(growable: false);
        }
        final rawMembers = await memberRepo.listMembers(
          conversationId: convId,
          limit: 200,
        );
        return rawMembers
            .where((m) => m.userId != currentUserId)
            .map(CallPickerParticipantRow.fromMember)
            .toList(growable: false);
      case _ParticipantSource.sameInterest:
        final page = await contactRepo.listContacts(limit: 100);
        return page.items
            .where((c) => c.userId != currentUserId)
            .map(CallPickerParticipantRow.fromContact)
            .toList(growable: false);
      case _ParticipantSource.otherGroups:
        final groupId = _selectedGroupId;
        if (groupId == null || groupId.isEmpty) {
          return const <CallPickerParticipantRow>[];
        }
        final rawMembers = await memberRepo.listMembers(
          conversationId: groupId,
          limit: 200,
        );
        return rawMembers
            .where((m) => m.userId != currentUserId)
            .map(CallPickerParticipantRow.fromMember)
            .toList(growable: false);
    }
  }

  void _applyDefaultSelectionIfNeeded(List<CallPickerParticipantRow> contacts) {
    final shouldSelectDefault =
        _source == _ParticipantSource.currentConversation &&
        widget.defaultSelectAll &&
        _selectedIds.isEmpty;
    if (!shouldSelectDefault) return;
    _selectedIds.addAll(
      contacts
          .map((c) => c.userId)
          .where((id) => id.isNotEmpty)
          .take(widget.selectionLimit),
    );
  }

  Future<void> _switchSource(_ParticipantSource next) async {
    if (!widget.allowsCrossContextSources &&
        next != _ParticipantSource.currentConversation) {
      return;
    }
    final previousSource = _source;
    setState(() {
      _source = next;
      _isLoading = true;
      _pageErrorSemantic = null;
    });
    try {
      final contacts = await _loadContactsForSource(next);
      if (!mounted) return;
      setState(() {
        _contacts = contacts;
        _isLoading = false;
        if (next == _ParticipantSource.currentConversation) {
          _selectedIds.clear();
          _applyDefaultSelectionIfNeeded(contacts);
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _source = previousSource;
        _isLoading = false;
      });
      await _showActionFailure(
        error,
        title: CallText.callSwitchInviteSourceFailed,
      );
    }
  }

  Future<void> _switchOtherGroup(String groupId) async {
    final previousGroupId = _selectedGroupId;
    setState(() {
      _selectedGroupId = groupId;
      _isLoading = true;
      _pageErrorSemantic = null;
    });
    try {
      final contacts = await _loadContactsForSource(
        _ParticipantSource.otherGroups,
      );
      if (!mounted) return;
      setState(() {
        _contacts = contacts;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _selectedGroupId = previousGroupId;
        _isLoading = false;
      });
      await _showActionFailure(
        error,
        title: CallText.callSwitchGroupMembersFailed,
      );
    }
  }

  Future<void> _showActionFailure(Object error, {required String title}) async {
    if (!mounted) {
      return;
    }
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: title,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction:
            resolved.primaryAction ??
            const UiErrorAction(
              type: UiErrorActionType.dismiss,
              label: FoundationText.confirm,
            ),
        secondaryAction: resolved.secondaryAction,
        dismissible: true,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
      ),
    );
  }

  List<CallPickerParticipantRow> get _filteredContacts {
    if (_searchQuery.isEmpty) return _contacts;
    final query = _searchQuery.toLowerCase();
    return _contacts.where((c) {
      return c.displayName.toLowerCase().contains(query);
    }).toList();
  }

  void _onConfirm() {
    if (_selectedIds.isEmpty) return;

    if (widget.routeExtra.isExistingCallInvite) {
      ref
          .read(callSessionProvider.notifier)
          .inviteToCall(_selectedIds.toList());
    }

    if (context.canPop()) {
      context.pop(_selectedIds.toList());
    }
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredContacts;
    final isDark = ref.watch(isDarkProvider);

    return AppScaffold(
      navigationBar: AppNavigationBar(
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: () {
            if (context.canPop()) context.pop();
          },
        ),
        middle: Text(
          CallText.callInviteParticipants,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _selectedIds.isNotEmpty ? _onConfirm : null,
          child: Text(
            UITextConstants.callConfirmSelected(_selectedIds.length),
            style: TextStyle(
              color: _selectedIds.isNotEmpty
                  ? AppColors.primaryColor
                  : AppColors.overlayLight,
              fontWeight: AppTypography.medium,
            ),
          ),
        ),
      ),
      child: SafeArea(
        child: _pageErrorSemantic != null && !_isLoading
            ? AppPageErrorState(
                semantic: ensureRetryUiErrorSemantic(_pageErrorSemantic!),
                onAction: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    await _loadContacts();
                  }
                },
              )
            : Column(
                children: [
                  if (widget.allowsCrossContextSources) _buildSourceTabs(),
                  if (_source == _ParticipantSource.otherGroups)
                    _buildGroupSelector(),
                  Padding(
                    padding: EdgeInsets.all(AppSpacing.md),
                    child: AppSearchField(
                      placeholder: CallText.callSearchContacts,
                      onChanged: (value) {
                        setState(() => _searchQuery = value);
                      },
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                    child: Row(
                      children: [
                        Text(
                          UITextConstants.callParticipantLimit(
                            widget.selectionLimit,
                          ),
                          style: TextStyle(
                            color: AppColors.overlayMedium,
                            fontSize: AppTypography.sm,
                          ),
                        ),
                        const Spacer(),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            setState(_selectedIds.clear);
                          },
                          child: Text(
                            CallText.callClearSelection,
                            style: TextStyle(
                              color: AppColors.overlayMedium,
                              fontSize: AppTypography.sm,
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.sm),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            setState(() {
                              _selectedIds.clear();
                              _applyDefaultSelectionIfNeeded(_contacts);
                            });
                          },
                          child: Text(
                            CallText.callRestoreDefaultSelection,
                            style: TextStyle(
                              color: AppColors.primaryColor,
                              fontSize: AppTypography.sm,
                              fontWeight: AppTypography.medium,
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.sm),
                        if (_selectedIds.isNotEmpty)
                          Text(
                            UITextConstants.callSelectedCount(
                              _selectedIds.length,
                            ),
                            style: TextStyle(
                              color: AppColors.primaryColor,
                              fontSize: AppTypography.sm,
                              fontWeight: AppTypography.medium,
                            ),
                          ),
                      ],
                    ),
                  ),
                  SizedBox(height: AppSpacing.sm),
                  Expanded(
                    child: _isLoading
                        ? AppRequestFeedback.section()
                        : filtered.isEmpty
                        ? Center(
                            child: Text(
                              _searchQuery.isEmpty
                                  ? CallText.callNoContacts
                                  : CallText.callNoMatchingContacts,
                              style: TextStyle(
                                color: AppColors.overlayMedium,
                                fontSize: AppTypography.md,
                              ),
                            ),
                          )
                        : ListView.builder(
                            itemCount: filtered.length,
                            itemBuilder: (context, index) {
                              final contact = filtered[index];
                              return _ContactRow(
                                contact: contact,
                                isSelected: _selectedIds.contains(
                                  contact.userId,
                                ),
                                isDisabled:
                                    _selectedIds.length >=
                                        widget.selectionLimit &&
                                    !_selectedIds.contains(contact.userId),
                                onToggle: (userId) {
                                  setState(() {
                                    if (_selectedIds.contains(userId)) {
                                      _selectedIds.remove(userId);
                                    } else if (_selectedIds.length <
                                        widget.selectionLimit) {
                                      _selectedIds.add(userId);
                                    }
                                  });
                                },
                              );
                            },
                          ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _buildSourceTabs() {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        AppSpacing.zero,
      ),
      child: CupertinoSlidingSegmentedControl<_ParticipantSource>(
        groupValue: _source,
        children: const <_ParticipantSource, Widget>{
          _ParticipantSource.currentConversation: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.six,
            ),
            child: Text(CallText.callSourceCurrentConversation),
          ),
          _ParticipantSource.sameInterest: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.six,
            ),
            child: Text(CallText.callSourceMutualFollow),
          ),
          _ParticipantSource.otherGroups: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.six,
            ),
            child: Text(CallText.callSourceOtherGroups),
          ),
        },
        onValueChanged: (value) {
          if (value != null) {
            _switchSource(value);
          }
        },
      ),
    );
  }

  Widget _buildGroupSelector() {
    if (_availableGroups.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: Text(
          CallText.callNoSwitchableConversation,
          style: TextStyle(
            color: AppColors.overlayMedium,
            fontSize: AppTypography.sm,
          ),
        ),
      );
    }
    return SizedBox(
      height: AppSpacing.forty,
      child: ListView.separated(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final group = _availableGroups[index];
          final groupId = group.id;
          final title = group.title.isNotEmpty ? group.title : groupId;
          final selected = groupId == _selectedGroupId;
          return GestureDetector(
            onTap: () => _switchOtherGroup(groupId),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.xs,
              ),
              decoration: BoxDecoration(
                color: selected
                    ? AppColors.primaryColor.withValues(alpha: 0.12)
                    : AppColors.white,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(
                  color: selected
                      ? AppColors.primaryColor
                      : AppColors.overlayLight,
                ),
              ),
              child: Center(
                child: Text(
                  title,
                  style: TextStyle(
                    color: selected
                        ? AppColors.primaryColor
                        : AppColors.overlayMedium,
                    fontSize: AppTypography.sm,
                    fontWeight: selected
                        ? AppTypography.semiBold
                        : AppTypography.medium,
                  ),
                ),
              ),
            ),
          );
        },
        separatorBuilder: (context, index) => SizedBox(width: AppSpacing.sm),
        itemCount: _availableGroups.length,
      ),
    );
  }
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({
    required this.contact,
    required this.isSelected,
    required this.isDisabled,
    required this.onToggle,
  });

  final CallPickerParticipantRow contact;
  final bool isSelected;
  final bool isDisabled;
  final ValueChanged<String> onToggle;

  @override
  Widget build(BuildContext context) {
    final userId = contact.userId;
    final displayName = contact.displayName.isNotEmpty
        ? contact.displayName
        : userId;
    final avatarUrl = contact.avatarUrl;

    return GestureDetector(
      onTap: isDisabled && !isSelected ? null : () => onToggle(userId),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: [
            Container(
              width: AppSpacing.iconMedium,
              height: AppSpacing.iconMedium,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isSelected
                    ? AppColors.primaryColor
                    : AppColors.transparent,
                border: Border.all(
                  color: isSelected
                      ? AppColors.primaryColor
                      : (isDisabled
                            ? AppColors.overlayLight
                            : AppColors.overlayMedium),
                  width: AppSpacing.oneHalf,
                ),
              ),
              child: isSelected
                  ? Icon(
                      CupertinoIcons.checkmark,
                      color: AppColors.white,
                      size: AppSpacing.iconSmall,
                    )
                  : null,
            ),
            SizedBox(width: AppSpacing.sm),
            AppCircularAvatar(
              imageUrl: avatarUrl,
              size: AppSpacing.twenty * 2,
              backgroundColor: AppColors.primaryColor.withValues(alpha: 0.2),
              fallback: Text(
                displayName.isNotEmpty ? displayName[0].toUpperCase() : '?',
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                displayName,
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.normal,
                  color: isDisabled && !isSelected
                      ? AppColors.overlayLight
                      : null,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
