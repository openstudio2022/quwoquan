import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_plan_capabilities.dart';

final class GatheringJourneyTemplate {
  GatheringJourneyTemplate({
    required this.templateId,
    required this.version,
    required this.title,
    required this.summary,
    required this.sourceDigest,
    required Iterable<GatheringPlanItem> items,
  }) : items = List<GatheringPlanItem>.unmodifiable(items);

  final String templateId;
  final int version;
  final String title;
  final String summary;
  final String sourceDigest;
  final List<GatheringPlanItem> items;
}

final class PutGatheringJourneyTemplateInput {
  PutGatheringJourneyTemplateInput({
    required this.idempotencyKey,
    required this.title,
    required this.summary,
    required this.sourceDigest,
    required Iterable<GatheringPlanItem> items,
    this.templateId,
    this.expectedVersion,
  }) : items = List<GatheringPlanItem>.unmodifiable(items);

  final String idempotencyKey;
  final String? templateId;
  final int? expectedVersion;
  final String title;
  final String summary;
  final String sourceDigest;
  final List<GatheringPlanItem> items;
}

abstract interface class GatheringJourneyTemplateQuery {
  Future<GatheringJourneyTemplate?> get(String templateId);

  Future<List<GatheringJourneyTemplate>> list();
}

abstract interface class GatheringJourneyTemplateWriter {
  Future<GatheringJourneyTemplate> put(PutGatheringJourneyTemplateInput input);
}
