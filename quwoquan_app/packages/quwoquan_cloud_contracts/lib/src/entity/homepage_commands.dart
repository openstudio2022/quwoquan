import '../operation_request_payload.dart';
import 'homepage_queries.dart';

// Homepage 用户侧命令与 claim/status_report 提交合约。
// 治理命令（intake/publish/claim review/report review）归 platform-ops，
// 不进入 App pure contracts。
export 'homepage_queries.dart'
    show HomepageDetailProjection, decodeHomepageDetail;

part '../generated/requests/entity/homepage_commands.requests.g.dart';

final class HomepageGeoPointInput {
  const HomepageGeoPointInput({required this.lat, required this.lng});

  final double lat;
  final double lng;
}

final class HomepageClaimRequestView {
  const HomepageClaimRequestView({
    required this.claimRequestId,
    required this.homepageId,
    required this.requesterPersonaId,
    required this.claimTier,
    required this.status,
    this.reviewNote,
    this.createdAt,
    this.reviewedAt,
  });

  final String claimRequestId;
  final String homepageId;
  final String requesterPersonaId;
  final String claimTier;
  final String status;
  final String? reviewNote;
  final DateTime? createdAt;
  final DateTime? reviewedAt;
}

HomepageClaimRequestView decodeHomepageClaimRequestView(Object? response) {
  final root = _expectObject(response, 'HomepageClaimRequest response');
  return HomepageClaimRequestView(
    claimRequestId: _requiredField(root, 'claimRequestId'),
    homepageId: _requiredField(root, 'homepageId'),
    requesterPersonaId: _requiredField(root, 'requesterPersonaId'),
    claimTier: _requiredField(root, 'claimTier'),
    status: _requiredField(root, 'status'),
    reviewNote: _optional(root['reviewNote'] as String?),
    createdAt: _optionalTimestamp(root['createdAt']),
    reviewedAt: _optionalTimestamp(root['reviewedAt']),
  );
}

final class HomepageStatusReportView {
  const HomepageStatusReportView({
    required this.reportId,
    required this.homepageId,
    required this.reporterPersonaId,
    required this.reason,
    required this.status,
    this.description,
    this.evidenceUrls = const <String>[],
    this.reviewNote,
    this.createdAt,
    this.reviewedAt,
  });

  final String reportId;
  final String homepageId;
  final String reporterPersonaId;
  final String reason;
  final String status;
  final String? description;
  final List<String> evidenceUrls;
  final String? reviewNote;
  final DateTime? createdAt;
  final DateTime? reviewedAt;
}

HomepageStatusReportView decodeHomepageStatusReportView(Object? response) {
  final root = _expectObject(response, 'HomepageStatusReport response');
  return HomepageStatusReportView(
    reportId: _requiredField(root, 'reportId'),
    homepageId: _requiredField(root, 'homepageId'),
    reporterPersonaId: _requiredField(root, 'reporterPersonaId'),
    reason: _requiredField(root, 'reason'),
    status: _requiredField(root, 'status'),
    description: _optional(root['description'] as String?),
    evidenceUrls: _stringList(root['evidenceUrls']),
    reviewNote: _optional(root['reviewNote'] as String?),
    createdAt: _optionalTimestamp(root['createdAt']),
    reviewedAt: _optionalTimestamp(root['reviewedAt']),
  );
}

abstract interface class HomepageCandidateCommandWriter {
  Future<HomepageDetailProjection> suggest(
    SuggestHomepageCandidateCommand command,
  );

  Future<HomepageDetailProjection> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  );
}

abstract interface class HomepageClaimRequestCommandWriter {
  Future<HomepageClaimRequestView> createClaimRequest(
    CreateHomepageClaimRequestCommand command,
  );
}

abstract interface class HomepageStatusReportCommandWriter {
  Future<HomepageStatusReportView> createStatusReport(
    CreateHomepageStatusReportCommand command,
  );
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$context must be a JSON object');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('missing required field "$key"');
  }
  return value.trim();
}

List<String> _stringList(Object? value) {
  if (value == null) return const <String>[];
  if (value is! List) {
    throw const FormatException('expected a string list');
  }
  return List<String>.unmodifiable(
    value.map((item) {
      if (item is! String) {
        throw const FormatException('expected a string list element');
      }
      return item;
    }),
  );
}

DateTime? _optionalTimestamp(Object? value) {
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) {
    throw const FormatException('timestamp must be an ISO-8601 string');
  }
  return DateTime.parse(value.trim()).toUtc();
}

String? _optional(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
