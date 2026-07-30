import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Canonical local-contract fixture for the typed atomic publication port.
final class RecordingContentPostPublicationWriter
    implements ContentPostPublicationWriter {
  final List<SubmitContentPostPublicationCommand> submitCommands =
      <SubmitContentPostPublicationCommand>[];

  Map<String, Object?>? get lastSubmitPayload {
    if (submitCommands.isEmpty) return null;
    final body = encodeContentPostSubmitPostPublicationGeneratedRequest(
      submitCommands.last,
    ).body;
    if (body is! Map) {
      throw StateError('encoded publication command body is not a map');
    }
    return body.map((key, value) => MapEntry(key.toString(), value));
  }

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    submitCommands.add(command);
    return ContentPostPublicationReceipt(
      publishIntentId: command.publishIntentId,
      localDraftId: command.localDraftId,
      postId: 'post_test_1',
      state: 'published',
      committedVersion: 1,
      acceptedAt: DateTime.utc(2030),
    );
  }
}
