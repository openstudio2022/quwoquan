import '../operation_request_payload.dart';
part '../generated/requests/content/report_commands.requests.g.dart';

/// Content Report command contract sourced from
/// `quwoquan_service/services/content-service/contracts/trust_safety/report`.
enum ContentReportTargetType { post, comment, user, circle, message }

/// Stable wire values from metadata `ReportReason`.
enum ContentReportReason { spam, harassment, violence, adult, copyright, other }



/// Content 举报 command capability.
abstract interface class ContentReportCommandWriter {
  Future<void> createReport(CreateContentReportCommand command);
}



void decodeEmptyCloudResponse(Object? _) {}
