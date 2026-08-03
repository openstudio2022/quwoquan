import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_template_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripTemplateItemIdFactory = String Function(TripPlanItemSlice item);
typedef TripTemplateIdempotencyKeyFactory = String Function();

final class TripTemplateCreateIntent {
  const TripTemplateCreateIntent({
    required this.request,
    required this.idempotencyKey,
  });

  final CreateTripPlanTemplateRequest request;
  final String idempotencyKey;
}

final class TripTemplateReviseIntent {
  const TripTemplateReviseIntent({
    required this.request,
    required this.idempotencyKey,
  });

  final PutTripPlanTemplateRequest request;
  final String idempotencyKey;
}

/// 从当前 Trip 冻结版本生成隐私安全模板；不复制成员、Moment、群消息或住宿细节。
final class TripTemplateCoordinator {
  const TripTemplateCoordinator({
    required this.facet,
    required this.itemIdFactory,
    required this.idempotencyKeyFactory,
  });

  final TripTemplateFacet facet;
  final TripTemplateItemIdFactory itemIdFactory;
  final TripTemplateIdempotencyKeyFactory idempotencyKeyFactory;

  TripTemplateCreateIntent prepare(
    TripJourneySnapshot snapshot, {
    required String title,
    String? summary,
  }) {
    if (!snapshot.usesOneCurrentRevision) {
      throw StateError('Trip projections do not use one current revision');
    }
    final normalizedTitle = title.trim();
    if (normalizedTitle.isEmpty || normalizedTitle.runes.length > 120) {
      throw ArgumentError.value(title, 'title', 'must contain 1-120 runes');
    }
    final planItems = snapshot.plan.items.toList(growable: false)
      ..sort((left, right) {
        final dayOrder = left.dayIndex.compareTo(right.dayIndex);
        return dayOrder == 0
            ? left.orderInDay.compareTo(right.orderInDay)
            : dayOrder;
      });
    if (planItems.isEmpty) {
      throw StateError('Trip must contain at least one plan item');
    }
    final dayCount = planItems
        .map((item) => item.dayIndex)
        .reduce((left, right) => left > right ? left : right);
    if (planItems.any((item) => item.dayIndex <= 0) || dayCount > 30) {
      throw StateError('Trip day index is outside template bounds');
    }

    final attributionById = <String, TripPlanSourceAttribution>{};
    for (final attribution in snapshot.plan.sourceAttributions) {
      if (attribution.attributionId.trim().isEmpty ||
          attribution.postId.trim().isEmpty ||
          attribution.title.trim().isEmpty ||
          attributionById.containsKey(attribution.attributionId)) {
        throw StateError('Trip source attribution is invalid');
      }
      if (attribution.kind ==
              TripPlanSourceAttributionKind.professionalCommentary &&
          (attribution.authorPersonaId ?? '').trim().isEmpty) {
        throw StateError('Professional attribution has no author');
      }
      attributionById[attribution.attributionId] = attribution;
    }
    final timelineItemById = <String, TripTimelineItemSlice>{
      for (final day in snapshot.timeline.days)
        for (final item in day.items) item.itemId: item,
    };
    final itemIds = <String>{};
    final templateItems = <TripPlanTemplateItem>[];
    for (final item in planItems) {
      final templateItemId = itemIdFactory(item).trim();
      if (templateItemId.isEmpty || !itemIds.add(templateItemId)) {
        throw StateError('Template item id must be unique and non-blank');
      }
      final linkedPostIds = timelineItemById[item.itemId]?.contentLinks
          .map((link) => link.postId)
          .toSet();
      final attributionIds =
          attributionById.values
              .where(
                (attribution) =>
                    linkedPostIds?.contains(attribution.postId) ?? false,
              )
              .map((attribution) => attribution.attributionId)
              .toList(growable: false)
            ..sort();
      final isStay = item.kind == TripPlanItemKind.stay;
      final publicPlace =
          !isStay &&
              item.placeRef?.objectTypeRef.trim() == 'entity.Place' &&
              item.placeRef!.objectId.trim().isNotEmpty
          ? TripPlanTemplatePlaceRef(
              objectTypeRef: 'entity.Place',
              objectId: item.placeRef!.objectId.trim(),
            )
          : null;
      final itemTitle = item.title.trim();
      templateItems.add(
        TripPlanTemplateItem(
          templateItemId: templateItemId,
          dayOffset: item.dayIndex - 1,
          orderInDay: item.orderInDay,
          kind: item.kind.wireName,
          title: isStay || itemTitle.isEmpty ? null : itemTitle,
          publicPlaceRef: publicPlace,
          note: null,
          attributionIds: attributionIds,
        ),
      );
    }
    final attributions =
        attributionById.values
            .map(
              (source) => TripPlanTemplateAttribution(
                attributionId: source.attributionId,
                kind: source.kind == TripPlanSourceAttributionKind.publicSource
                    ? TripPlanTemplateAttributionKind.publicSource
                    : TripPlanTemplateAttributionKind.professionalCommentary,
                referenceObjectTypeRef: 'content.Post',
                referenceObjectId: source.postId,
                authorPersonaId: source.authorPersonaId,
                title: source.title,
              ),
            )
            .toList(growable: false)
          ..sort(
            (left, right) => left.attributionId.compareTo(right.attributionId),
          );
    final idempotencyKey = idempotencyKeyFactory().trim();
    if (idempotencyKey.isEmpty) {
      throw StateError('Template idempotency key must not be blank');
    }
    final normalizedSummary = summary?.trim() ?? '';
    return TripTemplateCreateIntent(
      request: CreateTripPlanTemplateRequest(
        title: normalizedTitle,
        summary: normalizedSummary.isEmpty ? null : normalizedSummary,
        dayCount: dayCount,
        items: templateItems,
        attributions: attributions,
      ),
      idempotencyKey: idempotencyKey,
    );
  }

  Future<TripPlanTemplate> create(TripTemplateCreateIntent intent) {
    return facet.createTemplate(
      intent.request,
      idempotencyKey: intent.idempotencyKey,
    );
  }

  /// 修订模板说明时保留已经过隐私过滤的计划结构与署名，避免展示层重建
  /// items/attributions 时丢失专业作者和公开来源。
  TripTemplateReviseIntent prepareRevision(
    TripPlanTemplate template, {
    required String title,
    String? summary,
  }) {
    final templateId = template.id.trim();
    if (templateId.isEmpty || template.version <= 0) {
      throw StateError('Template identity and version must be valid');
    }
    if (template.dayCount <= 0 ||
        template.dayCount > 30 ||
        template.items.isEmpty) {
      throw StateError('Template structure is outside revision bounds');
    }
    final normalizedTitle = title.trim();
    if (normalizedTitle.isEmpty || normalizedTitle.runes.length > 120) {
      throw ArgumentError.value(title, 'title', 'must contain 1-120 runes');
    }
    final idempotencyKey = idempotencyKeyFactory().trim();
    if (idempotencyKey.isEmpty) {
      throw StateError('Template idempotency key must not be blank');
    }
    final normalizedSummary = summary?.trim() ?? '';
    return TripTemplateReviseIntent(
      request: PutTripPlanTemplateRequest(
        templateId: templateId,
        expectedVersion: template.version,
        title: normalizedTitle,
        summary: normalizedSummary.isEmpty ? null : normalizedSummary,
        dayCount: template.dayCount,
        items: template.items,
        attributions: template.attributions,
      ),
      idempotencyKey: idempotencyKey,
    );
  }

  Future<TripPlanTemplate> revise(TripTemplateReviseIntent intent) {
    return facet.reviseTemplate(
      intent.request,
      idempotencyKey: intent.idempotencyKey,
    );
  }
}
