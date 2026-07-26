import '../operation_request_payload.dart';

/// Content Report command contract sourced from
/// `quwoquan_service/services/content-service/contracts/trust_safety/report`.
enum ContentReportTargetType { post, comment, user, circle, message }

/// Stable wire values from metadata `ReportReason`.
enum ContentReportReason { spam, harassment, violence, adult, copyright, other }

/// Business-only command. Surface, route, actor and trace attribution belong to
/// [CloudOperationInvocationContext], not this payload.
final class CreateContentReportCommand {
  CreateContentReportCommand({
    required String targetId,
    required this.targetType,
    required this.reason,
    String? description,
  }) : targetId = _required(targetId, 'targetId'),
       description = _optional(description);

  final String targetId;
  final ContentReportTargetType targetType;
  final ContentReportReason reason;
  final String? description;

  static String _required(String value, String name) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(value, name, 'must not be empty');
    }
    return normalized;
  }

  static String? _optional(String? value) {
    final normalized = value?.trim() ?? '';
    return normalized.isEmpty ? null : normalized;
  }
}

/// Content 举报 command capability.
abstract interface class ContentReportCommandWriter {
  Future<void> createReport(CreateContentReportCommand command);
}

CloudOperationRequestPayload encodeCreateContentReportCommand(
  CreateContentReportCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'targetId': command.targetId,
      'targetType': command.targetType.name,
      'reason': command.reason.name,
      if (command.description != null) 'description': command.description,
    },
  );
}

void decodeEmptyCloudResponse(Object? _) {}
