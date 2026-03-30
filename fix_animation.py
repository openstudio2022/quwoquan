import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

old_animation = '''            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              height: _hideSecondaryTab ? 0 : AppSpacing.subTabNavigationHeight,
              child: SingleChildScrollView(
                physics: const NeverScrollableScrollPhysics(),
                child: _buildSubTabs(context, borderColor),
              ),
            ),'''

new_animation = '''            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              height: _hideSecondaryTab ? 0 : AppSpacing.subTabNavigationHeight,
              clipBehavior: Clip.hardEdge,
              decoration: const BoxDecoration(),
              child: _buildSubTabs(context, borderColor),
            ),'''

content = content.replace(old_animation, new_animation)

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(content)

