import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';

/// 群成员 `Map` 端侧过滤（无网络）。
List<Map<String, dynamic>> filterMemberMapsByQuery(
  List<Map<String, dynamic>> source,
  String query,
) {
  final q = query.trim();
  if (q.isEmpty) return List<Map<String, dynamic>>.from(source);

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

  return source.where((m) {
    final display = '${m['displayName'] ?? ''}';
    final name = '${m['name'] ?? ''}';
    final nickname = '${m['nickname'] ?? ''}';
    final userId = '${m['userId'] ?? ''}';
    return containsQuery(display) ||
        containsQuery(name) ||
        containsQuery(nickname) ||
        containsQuery(userId);
  }).toList(growable: false);
}

bool _isMostlyAscii(String s) {
  for (final c in s.runes) {
    if (c > 0x7F) return false;
  }
  return s.isNotEmpty;
}

/// 群成员 DTO 端侧过滤（无网络）。
List<ChatConversationMemberDto> filterMemberDtosByQuery(
  List<ChatConversationMemberDto> source,
  String query,
) {
  final q = query.trim();
  if (q.isEmpty) return List<ChatConversationMemberDto>.from(source);

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

  return source.where((m) {
    return containsQuery(m.displayName) || containsQuery(m.userId);
  }).toList(growable: false);
}
