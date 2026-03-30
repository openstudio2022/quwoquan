import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

enum _ParticipantSource { currentConversation, sameInterest, otherGroups }

class CallParticipantPickerPage extends ConsumerStatefulWidget {
  const CallParticipantPickerPage({
    super.key,
    this.callId,
    this.maxParticipants = 32,
    this.conversationId,
    this.defaultSelectAll = false,
  });

  final String? callId;
  final int maxParticipants;

  /// 群聊上下文：优先从群成员加载，忽略通用联系人
  final String? conversationId;

  /// 是否默认全选（群成员 <=8 时传 true）
  final bool defaultSelectAll;

  @override
  ConsumerState<CallParticipantPickerPage> createState() =>
      _CallParticipantPickerPageState();
}

class _CallParticipantPickerPageState
    extends ConsumerState<CallParticipantPickerPage> {
  final Set<String> _selectedIds = {};
  String _searchQuery = '';
  List<Map<String, dynamic>> _contacts = [];
  List<Map<String, dynamic>> _availableGroups = [];
  bool _isLoading = true;
  _ParticipantSource _source = _ParticipantSource.currentConversation;
  String? _selectedGroupId;

  @override
  void initState() {
    super.initState();
    _loadContacts();
  }

  Future<void> _loadContacts() async {
    try {
      final chatRepo = ref.read(chatRepositoryProvider);
      final contacts = await _loadContactsForSource(chatRepo, _source);
      final groups = await _loadAvailableGroups(chatRepo);
      if (mounted) {
        setState(() {
          _contacts = contacts;
          _availableGroups = groups;
          if (_selectedGroupId == null && groups.isNotEmpty) {
            _selectedGroupId =
                groups.first['id']?.toString() ??
                groups.first['_id']?.toString();
          }
          _isLoading = false;
          _applyDefaultSelectionIfNeeded(contacts);
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<List<Map<String, dynamic>>> _loadAvailableGroups(
    ChatRepository chatRepo,
  ) async {
    final inbox = await chatRepo.listInbox(limit: 100);
    final currentConversationId = widget.conversationId;
    return inbox
        .where((item) {
          return item.type == 'group' &&
              item.id.isNotEmpty &&
              item.id != currentConversationId;
        })
        .map((e) => e.toMap())
        .toList(growable: false);
  }

  Future<List<Map<String, dynamic>>> _loadContactsForSource(
    ChatRepository chatRepo,
    _ParticipantSource source,
  ) async {
    final currentUserId = ref.read(userDataProvider)?.id ?? '';
    switch (source) {
      case _ParticipantSource.currentConversation:
        final convId = widget.conversationId;
        if (convId == null || convId.isEmpty) {
          final rows = await chatRepo.listContacts(limit: 200);
          return rows.map((c) => c.toMap()).toList(growable: false);
        }
        final rawMembers = await chatRepo.listMembers(
          conversationId: convId,
          limit: 200,
        );
        return rawMembers
            .where((m) => m.userId != currentUserId)
            .map((m) => m.toMap())
            .toList(growable: false);
      case _ParticipantSource.sameInterest:
        final contacts = await chatRepo.listContacts(limit: 200);
        return contacts
            .where((c) => c.userId != currentUserId)
            .map((c) => c.toMap())
            .toList(growable: false);
      case _ParticipantSource.otherGroups:
        final groupId = _selectedGroupId;
        if (groupId == null || groupId.isEmpty) {
          return const <Map<String, dynamic>>[];
        }
        final rawMembers = await chatRepo.listMembers(
          conversationId: groupId,
          limit: 200,
        );
        return rawMembers
            .where((m) => m.userId != currentUserId)
            .map((m) => m.toMap())
            .toList(growable: false);
    }
  }

  void _applyDefaultSelectionIfNeeded(List<Map<String, dynamic>> contacts) {
    final shouldSelectDefault =
        _source == _ParticipantSource.currentConversation &&
        widget.defaultSelectAll &&
        _selectedIds.isEmpty;
    if (!shouldSelectDefault) return;
    _selectedIds.addAll(
      contacts
          .map((c) => c['userId'] as String? ?? '')
          .where((id) => id.isNotEmpty),
    );
  }

  Future<void> _switchSource(_ParticipantSource next) async {
    final chatRepo = ref.read(chatRepositoryProvider);
    setState(() {
      _source = next;
      _isLoading = true;
    });
    final contacts = await _loadContactsForSource(chatRepo, next);
    if (!mounted) return;
    setState(() {
      _contacts = contacts;
      _isLoading = false;
      if (next == _ParticipantSource.currentConversation) {
        _selectedIds.clear();
        _applyDefaultSelectionIfNeeded(contacts);
      }
    });
  }

  Future<void> _switchOtherGroup(String groupId) async {
    final chatRepo = ref.read(chatRepositoryProvider);
    setState(() {
      _selectedGroupId = groupId;
      _isLoading = true;
    });
    final contacts = await _loadContactsForSource(
      chatRepo,
      _ParticipantSource.otherGroups,
    );
    if (!mounted) return;
    setState(() {
      _contacts = contacts;
      _isLoading = false;
    });
  }

  List<Map<String, dynamic>> get _filteredContacts {
    if (_searchQuery.isEmpty) return _contacts;
    final query = _searchQuery.toLowerCase();
    return _contacts.where((c) {
      final name = (c['displayName'] as String? ?? '').toLowerCase();
      return name.contains(query);
    }).toList();
  }

  void _onConfirm() {
    if (_selectedIds.isEmpty) return;

    if (widget.callId != null) {
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
          '邀请参与者',
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _selectedIds.isNotEmpty ? _onConfirm : null,
          child: Text(
            '确定 (${_selectedIds.length})',
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
        child: Column(
            children: [
              _buildSourceTabs(),
              if (_source == _ParticipantSource.otherGroups)
                _buildGroupSelector(),
              Padding(
                padding: EdgeInsets.all(AppSpacing.md),
                child: AppSearchField(
                  placeholder: '搜索联系人',
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
                      '最多 ${widget.maxParticipants} 人',
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
                        UITextConstants.callClearSelection,
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
                        UITextConstants.callRestoreDefaultSelection,
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
                        '已选 ${_selectedIds.length}',
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
                    ? const Center(child: CupertinoActivityIndicator())
                    : filtered.isEmpty
                    ? Center(
                        child: Text(
                          _searchQuery.isEmpty ? '暂无联系人' : '未找到匹配的联系人',
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
                              contact['userId'] as String? ?? '',
                            ),
                            isDisabled:
                                _selectedIds.length >= widget.maxParticipants &&
                                !_selectedIds.contains(
                                  contact['userId'] as String? ?? '',
                                ),
                            onToggle: (userId) {
                              setState(() {
                                if (_selectedIds.contains(userId)) {
                                  _selectedIds.remove(userId);
                                } else if (_selectedIds.length <
                                    widget.maxParticipants) {
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
        0,
      ),
      child: CupertinoSlidingSegmentedControl<_ParticipantSource>(
        groupValue: _source,
        children: const <_ParticipantSource, Widget>{
          _ParticipantSource.currentConversation: Padding(
            padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Text(UITextConstants.callSourceCurrentConversation),
          ),
          _ParticipantSource.sameInterest: Padding(
            padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Text(UITextConstants.callSourceSameInterest),
          ),
          _ParticipantSource.otherGroups: Padding(
            padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Text(UITextConstants.callSourceOtherGroups),
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
          '暂无可切换群聊',
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
          final groupId =
              group['id']?.toString() ?? group['_id']?.toString() ?? '';
          final title = group['title']?.toString() ?? groupId;
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

  final Map<String, dynamic> contact;
  final bool isSelected;
  final bool isDisabled;
  final ValueChanged<String> onToggle;

  @override
  Widget build(BuildContext context) {
    final userId = contact['userId'] as String? ?? '';
    final displayName = contact['displayName'] as String? ?? userId;
    final avatarUrl = contact['avatarUrl'] as String?;

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
                color: isSelected ? AppColors.primaryColor : AppColors.transparent,
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
            CircleAvatar(
              radius: AppSpacing.twenty,
              backgroundColor: AppColors.primaryColor.withValues(alpha: 0.2),
              backgroundImage: avatarUrl != null
                  ? NetworkImage(avatarUrl)
                  : null,
              child: avatarUrl == null
                  ? Text(
                      displayName.isNotEmpty
                          ? displayName[0].toUpperCase()
                          : '?',
                      style: TextStyle(
                        fontSize: AppTypography.md,
                        fontWeight: AppTypography.semiBold,
                      ),
                    )
                  : null,
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
