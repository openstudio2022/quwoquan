import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 群主转让页 — 选择成员后确认弹窗
class TransferOwnershipPage extends ConsumerStatefulWidget {
  const TransferOwnershipPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<TransferOwnershipPage> createState() =>
      _TransferOwnershipPageState();
}

class _TransferOwnershipPageState
    extends ConsumerState<TransferOwnershipPage> {
  List<Map<String, dynamic>> _members = [];
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadMembers();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadMembers() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final members = await repo.listMembers(
        conversationId: widget.conversationId,
        limit: 200,
      );
      if (mounted) {
        setState(() {
          _members = members
              .where((m) => m['role'] != 'owner' && m['isCurrentUser'] != true)
              .toList();
        });
      }
    } catch (_) {}
  }

  void _onMemberSelected(Map<String, dynamic> member) {
    final name = member['displayName'] as String? ??
        member['name'] as String? ??
        '';

    showCupertinoDialog<void>(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        content: Text(
          '${UITextConstants.transferOwnershipConfirmPrefix}'
          '$name'
          '${UITextConstants.transferOwnershipConfirmSuffix}',
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(context),
          ),
          CupertinoDialogAction(
            child: Text(UITextConstants.confirm),
            onPressed: () async {
              Navigator.pop(context);
              try {
                final repo = ref.read(chatRepositoryProvider);
                await repo.transferOwnership(
                  widget.conversationId,
                  member['userId'] as String? ?? '',
                );
                if (mounted) context.pop();
              } catch (_) {}
            },
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    final filtered = _searchQuery.isEmpty
        ? _members
        : _members.where((m) {
            final name = (m['displayName'] ?? m['name'] ?? '') as String;
            return name.toLowerCase().contains(_searchQuery.toLowerCase());
          }).toList();

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        backgroundColor: bgColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          icon: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        title: Text(
          UITextConstants.selectNewOwner,
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            child: CupertinoSearchTextField(
              controller: _searchController,
              placeholder: UITextConstants.search,
              onChanged: (v) => setState(() => _searchQuery = v),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: filtered.length,
              itemBuilder: (context, i) {
                final m = filtered[i];
                final name = m['displayName'] as String? ??
                    m['name'] as String? ??
                    '';
                final avatar = m['avatarUrl'] as String? ??
                    m['avatar'] as String? ??
                    '';

                return Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () => _onMemberSelected(m),
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      child: Row(
                        children: [
                          RoundedSquareAvatar(
                            size: AppSpacing.largeButtonSize,
                            imageUrl: avatar,
                            name: name,
                          ),
                          SizedBox(width: AppSpacing.interGroupSm),
                          Expanded(
                            child: Text(
                              name,
                              style: TextStyle(
                                fontSize: AppTypography.lg,
                                color: fgPrimary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
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
