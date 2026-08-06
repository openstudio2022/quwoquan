import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Voice payload accepted by the reliable Message outbox.
///
/// The local recorder and temporary-file implementation stay private to the
/// Message object's presentation/platform composition.
final class QueuedChatVoice {
  const QueuedChatVoice({
    required this.filePath,
    required this.durationMs,
    required this.fileSize,
    required this.waveform,
  });

  final String filePath;
  final int durationMs;
  final int fileSize;
  final List<double> waveform;
}

/// Narrow lifecycle and retry surface of the Message send outbox.
abstract interface class ChatSendOutboxControl {
  Future<bool> enqueueCommand(ChatSendMessageCommand command);

  Future<bool> enqueueVoice({
    required String conversationId,
    required QueuedChatVoice voice,
  });

  Future<void> drain();

  Future<void> purgeForTerminalAccountClosure();
}
