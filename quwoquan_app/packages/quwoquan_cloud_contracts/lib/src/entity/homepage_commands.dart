import '../operation_request_payload.dart';
import 'homepage_queries.dart';

// Homepage 用户侧命令与 claim/status_report 提交合约。
// 治理命令（intake/publish/claim review/report review）归 platform-ops，
// 不进入 App pure contracts。
export 'homepage_queries.dart'
    show HomepageDetailProjection, decodeHomepageDetail;

final class HomepageGeoPointInput {
  const HomepageGeoPointInput({required this.lat, required this.lng});

  final double lat;
  final double lng;
}

final class SuggestHomepageCandidateCommand {
  SuggestHomepageCandidateCommand({
    required String title,
    required String homepageType,
    String? subtitle,
    List<String> categoryTags = const <String>[],
    String? coverUrl,
    String? address,
    String? city,
    String? sourcePlaceId,
    this.location,
  }) : title = _required(title, 'title'),
       homepageType = _required(homepageType, 'homepageType'),
       subtitle = _optional(subtitle),
       categoryTags = List<String>.unmodifiable(
         categoryTags.map((tag) => tag.trim()).where((tag) => tag.isNotEmpty),
       ),
       coverUrl = _optional(coverUrl),
       address = _optional(address),
       city = _optional(city),
       sourcePlaceId = _optional(sourcePlaceId);

  final String title;
  final String homepageType;
  final String? subtitle;
  final List<String> categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final String? sourcePlaceId;
  final HomepageGeoPointInput? location;
}

CloudOperationRequestPayload encodeSuggestHomepageCandidateCommand(
  SuggestHomepageCandidateCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'title': command.title,
      'homepageType': command.homepageType,
      if (command.subtitle case final subtitle?) 'subtitle': subtitle,
      if (command.categoryTags.isNotEmpty) 'categoryTags': command.categoryTags,
      if (command.coverUrl case final coverUrl?) 'coverUrl': coverUrl,
      if (command.address case final address?) 'address': address,
      if (command.city case final city?) 'city': city,
      if (command.sourcePlaceId case final sourcePlaceId?)
        'sourcePlaceId': sourcePlaceId,
      if (command.location case final location?)
        'location': <String, Object?>{'lat': location.lat, 'lng': location.lng},
    },
  );
}

final class UpdateClaimedHomepageBasicsCommand {
  UpdateClaimedHomepageBasicsCommand({
    required String homepageId,
    String? title,
    String? subtitle,
    List<String>? categoryTags,
    String? coverUrl,
    String? address,
    String? city,
    this.location,
  }) : homepageId = _required(homepageId, 'homepageId'),
       title = _optional(title),
       subtitle = _optional(subtitle),
       categoryTags = categoryTags == null
           ? null
           : List<String>.unmodifiable(
               categoryTags
                   .map((tag) => tag.trim())
                   .where((tag) => tag.isNotEmpty),
             ),
       coverUrl = _optional(coverUrl),
       address = _optional(address),
       city = _optional(city);

  final String homepageId;
  final String? title;
  final String? subtitle;
  final List<String>? categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final HomepageGeoPointInput? location;
}

CloudOperationRequestPayload encodeUpdateClaimedHomepageBasicsCommand(
  UpdateClaimedHomepageBasicsCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': command.homepageId},
    body: <String, Object?>{
      if (command.title case final title?) 'title': title,
      if (command.subtitle case final subtitle?) 'subtitle': subtitle,
      if (command.categoryTags case final categoryTags?)
        'categoryTags': categoryTags,
      if (command.coverUrl case final coverUrl?) 'coverUrl': coverUrl,
      if (command.address case final address?) 'address': address,
      if (command.city case final city?) 'city': city,
      if (command.location case final location?)
        'location': <String, Object?>{'lat': location.lat, 'lng': location.lng},
    },
  );
}

final class CreateHomepageClaimRequestCommand {
  CreateHomepageClaimRequestCommand({
    required String homepageId,
    required String claimTier,
    String? businessLicenseUrl,
    String? contactPhone,
    String? identityCardFrontUrl,
    String? identityCardBackUrl,
    String? note,
  }) : homepageId = _required(homepageId, 'homepageId'),
       claimTier = _required(claimTier, 'claimTier'),
       businessLicenseUrl = _optional(businessLicenseUrl),
       contactPhone = _optional(contactPhone),
       identityCardFrontUrl = _optional(identityCardFrontUrl),
       identityCardBackUrl = _optional(identityCardBackUrl),
       note = _optional(note);

  final String homepageId;
  final String claimTier;
  final String? businessLicenseUrl;
  final String? contactPhone;
  final String? identityCardFrontUrl;
  final String? identityCardBackUrl;
  final String? note;
}

CloudOperationRequestPayload encodeCreateHomepageClaimRequestCommand(
  CreateHomepageClaimRequestCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': command.homepageId},
    body: <String, Object?>{
      'claimTier': command.claimTier,
      if (command.businessLicenseUrl case final value?)
        'businessLicenseUrl': value,
      if (command.contactPhone case final value?) 'contactPhone': value,
      if (command.identityCardFrontUrl case final value?)
        'identityCardFrontUrl': value,
      if (command.identityCardBackUrl case final value?)
        'identityCardBackUrl': value,
      if (command.note case final value?) 'note': value,
    },
  );
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

final class CreateHomepageStatusReportCommand {
  CreateHomepageStatusReportCommand({
    required String homepageId,
    required String reason,
    String? description,
    List<String> evidenceUrls = const <String>[],
  }) : homepageId = _required(homepageId, 'homepageId'),
       reason = _required(reason, 'reason'),
       description = _optional(description),
       evidenceUrls = List<String>.unmodifiable(
         evidenceUrls.map((url) => url.trim()).where((url) => url.isNotEmpty),
       );

  final String homepageId;
  final String reason;
  final String? description;
  final List<String> evidenceUrls;
}

CloudOperationRequestPayload encodeCreateHomepageStatusReportCommand(
  CreateHomepageStatusReportCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': command.homepageId},
    body: <String, Object?>{
      'reason': command.reason,
      if (command.description case final value?) 'description': value,
      if (command.evidenceUrls.isNotEmpty) 'evidenceUrls': command.evidenceUrls,
    },
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

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}

String? _optional(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
