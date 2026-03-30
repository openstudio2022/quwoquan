import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

# Fix 1: Remove AnimatedSlide and AnimatedOpacity, use AnimatedContainer
old_animation = '''            AnimatedSlide(
              offset: _hideSecondaryTab ? const Offset(0, -1) : Offset.zero,
              duration: const Duration(milliseconds: 200),
              child: AnimatedOpacity(
                opacity: _hideSecondaryTab ? 0 : 1,
                duration: const Duration(milliseconds: 200),
                child: _buildSubTabs(context, borderColor),
              ),
            ),'''

new_animation = '''            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              height: _hideSecondaryTab ? 0 : AppSpacing.subTabNavigationHeight,
              child: SingleChildScrollView(
                physics: const NeverScrollableScrollPhysics(),
                child: _buildSubTabs(context, borderColor),
              ),
            ),'''

content = content.replace(old_animation, new_animation)

# Fix 2: Secret Chat Content
old_secret = '''  Widget _buildSecretMessageContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    if (!_secretUnlocked) {
      return _buildSecretLockScreen(context, fgPrimary, fgSecondary);
    }
    final encrypted = ref
        .read(appContentRepositoryProvider)
        .chatEncryptedConversations;
    return Column(
      children: [
        Container(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: 12,
          ),
          decoration: BoxDecoration(
            color: AppColors.primaryColor.withValues(alpha: 0.08),
            border: Border(
              bottom: BorderSide(color: borderColor.withValues(alpha: 0.2)),
            ),
          ),
          child: Row(
            children: [
              Icon(
                Icons.shield,
                color: AppColors.primaryColor,
                size: AppSpacing.iconMedium,
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.secretUnlockedBanner,
                      style: TextStyle(
                        fontSize: AppTypography.md,
                        fontWeight: FontWeight.w700,
                        color: fgPrimary,
                      ),
                    ),
                    Text(
                      '${encrypted.length} 个加密对话 · 安全保护中',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _secretLock,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.lock,
                      size: AppSpacing.iconSmall,
                      color: AppColors.primaryColor,
                    ),
                    SizedBox(width: AppSpacing.xs),
                    Text(
                      UITextConstants.secretLockButton,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: encrypted.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.shield_outlined,
                        size: AppSpacing.largeButtonSize,
                        color: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Text(
                        UITextConstants.noSecretConversations,
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: encrypted.length,
                  itemBuilder: (context, i) {
                    final c = encrypted[i];
                    return _ConversationTile(
                      conversation: c,
                      isSpecial: false,
                      onTap: () => context.push(
                        AppRoutePaths.chatDetail(id: '${c['id']}'),
                      ),
                      fgPrimary: fgPrimary,
                      fgSecondary: fgSecondary,
                      borderColor: borderColor,
                      showEncryptedBadge: true,
                    );
                  },
                ),
        ),
      ],
    );
  }'''

new_secret = '''  Widget _buildSecretMessageContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    if (!_secretUnlocked) {
      return _buildSecretLockScreen(context, fgPrimary, fgSecondary);
    }
    final encrypted = ref
        .read(appContentRepositoryProvider)
        .chatEncryptedConversations;
    
    if (encrypted.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.chat_bubble_outline,
              size: AppSpacing.iconButtonMinSizeMd,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              '暂无密信对话',
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollController,
      itemCount: encrypted.length,
      itemBuilder: (context, i) {
        final c = encrypted[i];
        return _ConversationTile(
          conversation: c,
          isSpecial: false,
          onTap: () => context.push(
            AppRoutePaths.chatDetail(id: '${c['id']}'),
          ),
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          borderColor: borderColor,
          showEncryptedBadge: false, // Do not show lock icon
        );
      },
    );
  }'''

content = content.replace(old_secret, new_secret)

# Fix 3: Empty state text for MessagesContent
old_empty = '''    if (convs.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.chat_bubble_outline,
              size: AppSpacing.iconButtonMinSizeMd,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              UITextConstants.noConversations,
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
            Text(
              UITextConstants.startChatHint,
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
          ],
        ),
      );
    }'''

new_empty = '''    if (convs.isEmpty) {
      final sub = _messageSubTabs[_subTabIndex];
      String title = '';
      String subtitle = '';
      
      if (sub == '全部') {
        title = '暂无对话';
        subtitle = '开始与圈友聊天吧！';
      } else if (sub == '@我') {
        title = '暂无@我的消息';
      } else if (sub == '未读') {
        title = '暂无未读消息';
      }
      
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.chat_bubble_outline,
              size: AppSpacing.iconButtonMinSizeMd,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              title,
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
            if (subtitle.isNotEmpty)
              Text(
                subtitle,
                style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
              ),
          ],
        ),
      );
    }'''

content = content.replace(old_empty, new_empty)

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(content)

