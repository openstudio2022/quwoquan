import 'package:quwoquan_app/assistant/transcript/identity/transcript_line_id.dart';
import 'package:quwoquan_app/assistant/transcript/user_utterance/utterance_send_state.dart';

/// 用户侧 utterance 快照（C2）。不含 runArtifacts / journey。
class UserUtterance {
  const UserUtterance({
    required this.text,
    this.personaId = '',
    this.sendState = UtteranceSendState.sent,
  });

  final String text;
  final String personaId;
  final UtteranceSendState sendState;

  UserUtterance copyWith({
    String? text,
    String? personaId,
    UtteranceSendState? sendState,
  }) {
    return UserUtterance(
      text: text ?? this.text,
      personaId: personaId ?? this.personaId,
      sendState: sendState ?? this.sendState,
    );
  }
}

/// 信封级展示字段（与 UI Map 的 sender* 对齐）。
class UserUtteranceEnvelope {
  const UserUtteranceEnvelope({
    required this.id,
    required this.conversationId,
    required this.senderId,
    required this.senderName,
    this.senderAvatar = '',
    this.timestamp = '',
    required this.utterance,
  });

  final TranscriptLineId id;
  final String conversationId;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String timestamp;
  final UserUtterance utterance;
}
