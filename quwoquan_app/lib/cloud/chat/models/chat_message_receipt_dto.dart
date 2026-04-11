/// 消息已读回执行（GetReceipts）。
class ChatMessageReceiptDto {
  const ChatMessageReceiptDto({
    required this.userId,
    this.readAt,
  });

  final String userId;
  final DateTime? readAt;

  factory ChatMessageReceiptDto.fromMap(Map<String, dynamic> m) {
    return ChatMessageReceiptDto(
      userId: (m['userId'] ?? m['readerId'] ?? '').toString(),
      readAt: m['readAt'] != null
          ? DateTime.tryParse(m['readAt'].toString())
          : null,
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'userId': userId,
        if (readAt != null) 'readAt': readAt!.toIso8601String(),
      };
}
