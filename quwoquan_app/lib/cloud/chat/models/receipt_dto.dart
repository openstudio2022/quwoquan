/// Typed DTO for the MessageReceipt entity.
/// Maps to contracts/metadata/messages/conversation/fields.yaml → MessageReceipt.
class ReceiptDto {
  final String id;
  final String messageId;
  final String conversationId;
  final String userId;
  final DateTime readAt;

  const ReceiptDto({
    required this.id,
    required this.messageId,
    required this.conversationId,
    required this.userId,
    required this.readAt,
  });

  factory ReceiptDto.fromMap(Map<String, dynamic> map) {
    return ReceiptDto(
      id: (map['_id'] ?? map['id'] ?? '') as String,
      messageId: (map['messageId'] ?? '') as String,
      conversationId: (map['conversationId'] ?? '') as String,
      userId: (map['userId'] ?? '') as String,
      readAt: DateTime.tryParse((map['readAt'] ?? '') as String) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'messageId': messageId,
        'conversationId': conversationId,
        'userId': userId,
        'readAt': readAt.toIso8601String(),
      };
}
