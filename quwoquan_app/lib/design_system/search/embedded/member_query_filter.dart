import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";

bool _isMostlyAscii(String s) {
  for (final c in s.runes) {
    if (c > 0x7F) return false;
  }
  return s.isNotEmpty;
}

/// 群成员 DTO 端侧过滤（无网络）。
List<ConversationMemberListRow> filterMemberDtosByQuery(
  List<ConversationMemberListRow> source,
  String query,
) {
  final q = query.trim();
  if (q.isEmpty) return List<ConversationMemberListRow>.from(source);

  final lower = q.toLowerCase();
  bool containsQuery(String? s) {
    if (s == null || s.isEmpty) return false;
    final t = s.trim();
    if (t.isEmpty) return false;
    if (_isMostlyAscii(t)) {
      return t.toLowerCase().contains(lower);
    }
    return t.contains(q);
  }

  return source
      .where((m) {
        return containsQuery(m.displayName) || containsQuery(m.userId);
      })
      .toList(growable: false);
}
