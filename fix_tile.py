import re

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'r') as f:
    content = f.read()

content = content.replace("showEncryptedBadge || conversation['type'] == 'encrypted';", "showEncryptedBadge;")

with open('quwoquan_app/lib/ui/chat/pages/chat_page.dart', 'w') as f:
    f.write(content)

