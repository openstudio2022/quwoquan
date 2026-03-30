/// 发起群聊向导中的可选成员（ViewModel，非云 DTO）。
class StartGroupPickableMember {
  const StartGroupPickableMember({
    required this.userId,
    required this.displayName,
    required this.avatarUrl,
  });

  final String userId;
  final String displayName;
  final String avatarUrl;
}

/// 联系人列表按首字母分组用的一行（仅 UI）。
class StartGroupFriendLetterRow {
  const StartGroupFriendLetterRow({
    required this.displayName,
    required this.userId,
    required this.avatarUrl,
    required this.letter,
  });

  final String displayName;
  final String userId;
  final String avatarUrl;
  final String letter;
}
