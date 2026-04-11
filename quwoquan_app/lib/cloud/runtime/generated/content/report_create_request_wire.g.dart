// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/report/fields.yaml (CreateReport API body keys)
// aligned with ContentApiMetadata.createReportPath payload.
// Regenerate: make codegen-app

class CreateReportRequestWire {
  const CreateReportRequestWire({
    required this.targetId,
    required this.targetType,
    required this.reason,
    this.description,
  });

  final String targetId;
  final String targetType;
  final String reason;
  final String? description;

  Map<String, dynamic> toMap() => <String, dynamic>{
        'targetId': targetId,
        'targetType': targetType,
        'reason': reason,
        if (description != null && description!.isNotEmpty)
          'description': description,
      };
}
