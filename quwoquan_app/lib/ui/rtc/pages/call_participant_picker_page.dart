import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

class CallParticipantPickerPage extends ConsumerStatefulWidget {
  const CallParticipantPickerPage({
    super.key,
    this.callId,
    this.maxParticipants = 32,
  });

  final String? callId;
  final int maxParticipants;

  @override
  ConsumerState<CallParticipantPickerPage> createState() =>
      _CallParticipantPickerPageState();
}

class _CallParticipantPickerPageState
    extends ConsumerState<CallParticipantPickerPage> {
  final Set<String> _selectedIds = {};
  String _searchQuery = '';
  List<Map<String, dynamic>> _contacts = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadContacts();
  }

  Future<void> _loadContacts() async {
    try {
      final chatRepo = ref.read(chatRepositoryProvider);
      final contacts = await chatRepo.listContacts();
      if (mounted) {
        setState(() {
          _contacts = contacts;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  List<Map<String, dynamic>> get _filteredContacts {
    if (_searchQuery.isEmpty) return _contacts;
    final query = _searchQuery.toLowerCase();
    return _contacts.where((c) {
      final name =
          (c['displayName'] as String? ?? '').toLowerCase();
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

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            if (context.canPop()) context.pop();
          },
          child: const Icon(CupertinoIcons.xmark),
        ),
        middle: const Text('邀请参与者'),
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
            Padding(
              padding: EdgeInsets.all(AppSpacing.md),
              child: CupertinoSearchTextField(
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
                              isDisabled: _selectedIds.length >=
                                      widget.maxParticipants &&
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
                color: isSelected
                    ? AppColors.primaryColor
                    : Colors.transparent,
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
              backgroundColor:
                  AppColors.primaryColor.withValues(alpha: 0.2),
              backgroundImage:
                  avatarUrl != null ? NetworkImage(avatarUrl) : null,
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
