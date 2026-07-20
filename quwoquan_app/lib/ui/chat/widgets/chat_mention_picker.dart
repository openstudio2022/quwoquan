import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/input/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ChatMentionPicker extends StatefulWidget {
  const ChatMentionPicker({
    super.key,
    required this.currentUserId,
    required this.allowMentionAll,
    required this.searchMembers,
  });

  final String currentUserId;
  final bool allowMentionAll;
  final Future<List<ChatConversationMemberDto>> Function(String query)
  searchMembers;

  static Future<ChatInputMentionCandidate?> show(
    BuildContext context, {
    required String currentUserId,
    required bool allowMentionAll,
    required Future<List<ChatConversationMemberDto>> Function(String query)
    searchMembers,
  }) {
    return showCupertinoModalPopup<ChatInputMentionCandidate>(
      context: context,
      builder: (context) => ChatMentionPicker(
        currentUserId: currentUserId,
        allowMentionAll: allowMentionAll,
        searchMembers: searchMembers,
      ),
    );
  }

  @override
  State<ChatMentionPicker> createState() => _ChatMentionPickerState();
}

class _ChatMentionPickerState extends State<ChatMentionPicker> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;
  List<ChatConversationMemberDto> _members =
      const <ChatConversationMemberDto>[];
  bool _isLoading = true;
  String? _error;
  int _requestSerial = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_search(''));
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(
      const Duration(milliseconds: 250),
      () => unawaited(_search(value)),
    );
  }

  Future<void> _search(String rawQuery) async {
    final serial = ++_requestSerial;
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final members = await widget.searchMembers(rawQuery.trim());
      if (!mounted || serial != _requestSerial) {
        return;
      }
      setState(() {
        _members = members
            .where(
              (member) =>
                  member.userId.trim().isNotEmpty &&
                  member.userId != widget.currentUserId &&
                  member.memberType != 'assistant' &&
                  member.userId != 'assistant',
            )
            .take(50)
            .toList(growable: false);
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted || serial != _requestSerial) {
        return;
      }
      setState(() {
        _isLoading = false;
        _error = runtimeErrorDisplayMessage(error);
      });
    }
  }

  bool get _showMentionAll {
    if (!widget.allowMentionAll) {
      return false;
    }
    final query = _searchController.text.trim().toLowerCase();
    return query.isEmpty ||
        ChatText.mentionAll.toLowerCase().contains(query) ||
        '__all__'.contains(query);
  }

  @override
  Widget build(BuildContext context) {
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final separator = CupertinoColors.separator.resolveFrom(context);
    return Material(
      color: AppColors.transparent,
      child: SafeArea(
        top: false,
        child: FractionallySizedBox(
          heightFactor: 0.68,
          alignment: Alignment.bottomCenter,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: background,
              borderRadius: BorderRadius.vertical(
                top: Radius.circular(AppSpacing.largeBorderRadius),
              ),
            ),
            child: Column(
              children: [
                Padding(
                  padding: EdgeInsets.fromLTRB(
                    AppSpacing.containerMd,
                    AppSpacing.md,
                    AppSpacing.containerSm,
                    AppSpacing.sm,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          ChatText.mentionPickerTitle,
                          style: TextStyle(
                            fontSize: AppTypography.iosNavTitle,
                            fontWeight: AppTypography.semiBold,
                            color: CupertinoColors.label.resolveFrom(context),
                          ),
                        ),
                      ),
                      CupertinoButton(
                        padding: EdgeInsets.all(AppSpacing.sm),
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Icon(CupertinoIcons.xmark),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  child: CupertinoSearchTextField(
                    controller: _searchController,
                    placeholder: ChatText.searchGroupMembers,
                    onChanged: _onQueryChanged,
                  ),
                ),
                SizedBox(height: AppSpacing.sm),
                Divider(height: AppSpacing.hairline, color: separator),
                Expanded(child: _buildResults(context)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildResults(BuildContext context) {
    if (_isLoading && _members.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error case final error?) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error.isEmpty ? ChatText.mentionPickerLoadFailed : error,
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.md),
              CupertinoButton.filled(
                onPressed: () => unawaited(_search(_searchController.text)),
                child: const Text(ChatText.mentionPickerRetry),
              ),
            ],
          ),
        ),
      );
    }
    if (_members.isEmpty && !_showMentionAll) {
      return const Center(child: Text(ChatText.noMatchingMembers));
    }
    return ListView(
      children: [
        if (_showMentionAll)
          _MentionCandidateRow(
            icon: CupertinoIcons.person_3_fill,
            title: ChatText.mentionAll,
            subtitle: ChatText.mentionAllDescription,
            onTap: () => Navigator.of(context).pop(
              const ChatInputMentionCandidate(
                id: '__all__',
                displayName: ChatText.mentionAll,
                kind: ChatInputMentionKind.all,
              ),
            ),
          ),
        for (final member in _members)
          _MentionCandidateRow(
            avatarUrl: member.avatarUrl,
            title: member.displayName.trim().isEmpty
                ? member.userId
                : member.displayName.trim(),
            subtitle: member.role,
            onTap: () => Navigator.of(context).pop(
              ChatInputMentionCandidate(
                id: member.userId,
                displayName: member.displayName.trim().isEmpty
                    ? member.userId
                    : member.displayName.trim(),
                avatarUrl: member.avatarUrl,
              ),
            ),
          ),
      ],
    );
  }
}

class _MentionCandidateRow extends StatelessWidget {
  const _MentionCandidateRow({
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.avatarUrl = '',
    this.icon,
  });

  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final String avatarUrl;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      onPressed: onTap,
      child: Row(
        children: [
          if (icon case final resolvedIcon?)
            Container(
              width: AppSpacing.avatarUserMd,
              height: AppSpacing.avatarUserMd,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
              ),
              child: Icon(resolvedIcon, color: AppColors.primaryColor),
            )
          else
            RoundedSquareAvatar(
              size: AppSpacing.avatarUserMd,
              imageUrl: avatarUrl.trim().isEmpty ? null : avatarUrl,
              name: title,
            ),
          SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: CupertinoColors.label.resolveFrom(context),
                    fontSize: AppTypography.iosBody,
                  ),
                ),
                if (subtitle.trim().isNotEmpty)
                  Text(
                    subtitle,
                    style: TextStyle(
                      color: secondary,
                      fontSize: AppTypography.iosFootnote,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
