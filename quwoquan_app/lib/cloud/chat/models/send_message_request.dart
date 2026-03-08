/// Request payload for sending a message.
/// Maps to the POST /v1/chat/conversations/:id/messages request body.
class SendMessageRequest {
  final String type;
  final String content;
  final String? mediaUrl;
  final Map<String, dynamic>? media;
  final Map<String, dynamic>? cardPayload;
  final String? replyToMessageId;
  final List<String>? mentions;
  final String clientMsgId;

  const SendMessageRequest({
    required this.type,
    required this.content,
    this.mediaUrl,
    this.media,
    this.cardPayload,
    this.replyToMessageId,
    this.mentions,
    required this.clientMsgId,
  });

  Map<String, dynamic> toMap() => {
        'type': type,
        'content': content,
        'clientMsgId': clientMsgId,
        if (mediaUrl != null) 'mediaUrl': mediaUrl,
        if (media != null) 'media': media,
        if (cardPayload != null) 'cardPayload': cardPayload,
        if (replyToMessageId != null) 'replyToMessageId': replyToMessageId,
        if (mentions != null) 'mentions': mentions,
      };
}
