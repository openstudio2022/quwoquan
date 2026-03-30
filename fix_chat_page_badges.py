import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

old_subtabs = '''  Widget _buildSubTabs(BuildContext context, Color borderColor) {
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;
    return SecondaryCapsuleTabBar(
      isDark: ref.read(isDarkProvider),
      tabs: subTabs,
      activeIndex: _subTabIndex,
      onTap: (index) => setState(() => _subTabIndex = index),
      horizontalPadding: AppSpacing.feedContentHorizontal(context),
      border: Border(
        bottom: BorderSide(color: borderColor.withValues(alpha: 0.2)),
      ),
    );
  }'''

new_subtabs = '''  Widget _buildSubTabs(BuildContext context, Color borderColor) {
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;
    
    Map<int, int>? numberBadges;
    Map<int, bool>? dotBadges;

    if (_mainTabIndex == 0 && _conversations != null) {
      int atMeCount = 0;
      int unreadCount = 0;
      bool hasSecretUnread = false;

      for (final c in _conversations!) {
        final isSecret = c['type'] == 'encrypted';
        final unread = c['unreadCount'] as int? ?? 0;
        final hasMention = c['hasMention'] == true;

        if (isSecret) {
          if (unread > 0 || hasMention) {
            hasSecretUnread = true;
          }
        } else {
          if (hasMention) {
            atMeCount += unread > 0 ? unread : 1;
          }
          unreadCount += unread;
        }
      }

      numberBadges = {};
      dotBadges = {};

      final atMeIndex = _messageSubTabs.indexOf('@我');
      if (atMeIndex != -1 && atMeCount > 0) {
        numberBadges[atMeIndex] = atMeCount;
      }

      final unreadIndex = _messageSubTabs.indexOf('未读');
      if (unreadIndex != -1 && unreadCount > 0) {
        numberBadges[unreadIndex] = unreadCount;
      }

      final secretIndex = _messageSubTabs.indexOf('密信');
      if (secretIndex != -1 && hasSecretUnread) {
        dotBadges[secretIndex] = true;
      }
    }

    return SecondaryCapsuleTabBar(
      isDark: ref.read(isDarkProvider),
      tabs: subTabs,
      activeIndex: _subTabIndex,
      onTap: (index) => setState(() => _subTabIndex = index),
      horizontalPadding: AppSpacing.feedContentHorizontal(context),
      border: Border(
        bottom: BorderSide(color: borderColor.withValues(alpha: 0.2)),
      ),
      numberBadges: numberBadges,
      dotBadges: dotBadges,
    );
  }'''

content = content.replace(old_subtabs, new_subtabs)

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(content)

