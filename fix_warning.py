import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

old_lock = '''  void _secretLock() {
    setState(() {
      _secretUnlocked = false;
      _secretAuthError = '';
    });
  }'''

content = content.replace(old_lock, '')

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(content)

