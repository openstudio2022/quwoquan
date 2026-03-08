/// Response payload after sending a message.
/// Maps to the POST /v1/chat/conversations/:id/messages response.
class SendMessageResponse {
  final String id;
  final int seq;
  final DateTime timestamp;

  const SendMessageResponse({
    required this.id,
    required this.seq,
    required this.timestamp,
  });

  factory SendMessageResponse.fromMap(Map<String, dynamic> map) {
    return SendMessageResponse(
      id: (map['messageId'] ?? map['_id'] ?? map['id'] ?? '') as String,
      seq: (map['seq'] as num?)?.toInt() ?? 0,
      timestamp: DateTime.tryParse((map['timestamp'] ?? '') as String) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'seq': seq,
        'timestamp': timestamp.toIso8601String(),
      };
}
