import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

new_tile = '''class _ConversationTile extends StatelessWidget {
  final Map<String, dynamic> conversation;
  final bool isSpecial;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color borderColor;
  final bool showEncryptedBadge;

  const _ConversationTile({
    required this.conversation,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.borderColor,
    this.isSpecial = false,
    this.showEncryptedBadge = false,
  });

  static const double _avatarSize = 48;

  String _formatConversationTime(Map<String, dynamic> conv) {
    final isoStr =
        conv['lastMessageAt'] as String? ??
        conv['lastMessageTime'] as String? ??
        conv['updatedAt'] as String?;
    final dt = ChatTimeFormatter.tryParseServerTime(isoStr);
    if (dt == null) return '';
    return ChatTimeFormatter.formatForConversationList(dt);
  }

  Widget _buildConversationAvatar() {
    final type = conversation['type'] as String? ?? 'direct';
    final isGroup = type == 'group';

    if (isGroup) {
      final memberAvatars =
          (conversation['memberAvatars'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          <String>[];
      return GroupAvatarGrid(size: _avatarSize, avatarUrls: memberAvatars);
    }

    return RoundedSquareAvatar(
      size: _avatarSize,
      imageUrl:
          conversation['avatar'] as String? ??
          conversation['avatarUrl'] as String? ??
          '',
      name: conversation['title'] as String? ?? '',
    );
  }

  @override
  Widget build(BuildContext context) {
    final unread = conversation['unreadCount'] as int? ?? 0;
    final isEncrypted =
        showEncryptedBadge || conversation['type'] == 'encrypted';
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: borderColor.withValues(alpha: 0.3), width: 0.5),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                _buildConversationAvatar(),
                if (isEncrypted)
                  Positioned(
                    right: -2,
                    bottom: -2,
                    child: Container(
                      padding: EdgeInsets.all(2),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: Theme.of(context).scaffoldBackgroundColor,
                          width: 1.5,
                        ),
                      ),
                      child: Icon(
                        Icons.lock,
                        size: 10,
                        color: Colors.white,
                      ),
                    ),
                  ),
                if (unread > 0)
                  Positioned(
                    right: -6,
                    top: -6,
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: unread > 9 ? 5 : 4,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.error,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: Theme.of(context).scaffoldBackgroundColor,
                          width: 1.5,
                        ),
                      ),
                      child: Text(
                        unread > 99 ? '99+' : '$unread',
                        style: TextStyle(
                          fontSize: 10,
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          height: 1.1,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Flexible(
                              child: Text(
                                conversation['title'] as String? ?? '',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w500,
                                  color: fgPrimary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (isSpecial) ...[
                              SizedBox(width: 4),
                              Container(
                                padding: EdgeInsets.symmetric(
                                  horizontal: 4,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: AppColors.warning.withValues(alpha: 0.2),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  'AI',
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.warning,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      SizedBox(width: 8),
                      Text(
                        _formatConversationTime(conversation),
                        style: TextStyle(
                          fontSize: 12,
                          color: fgSecondary.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 4),
                  Row(
                    children: [
                      if (isEncrypted) ...[
                        Icon(
                          Icons.lock,
                          size: 14,
                          color: fgSecondary.withValues(alpha: 0.8),
                        ),
                        SizedBox(width: 4),
                      ],
                      Expanded(
                        child: Text(
                          conversation['lastMessage'] as String? ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 14,
                            color: fgSecondary.withValues(alpha: 0.8),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}'''

pattern = re.compile(r'class _ConversationTile extends StatelessWidget \{.*?\n\}\n', re.DOTALL)
new_content = pattern.sub(new_tile + '\n', content)

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(new_content)

