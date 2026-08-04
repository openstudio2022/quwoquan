// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_facet.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/travel/pages/trip_templates_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets(
    'organizer revises template description without losing structure',
    (tester) async {
      final facet = _TemplateFacet();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            tripTemplateFacetProvider.overrideWithValue(facet),
            tripTemplateCoordinatorProvider.overrideWithValue(
              TripTemplateCoordinator(
                facet: facet,
                itemIdFactory: (item) => 'template-${item.itemId}',
                idempotencyKeyFactory: () => 'template-revise-intent-1',
              ),
            ),
          ],
          child: MaterialApp(
            home: TripTemplatesPage(onBack: () {}, onOpenTrip: (_) {}),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('西湖两日模板'), findsOneWidget);
      await tester.tap(find.text('修改模板说明'));
      await tester.pumpAndSettle();
      final titleField = find.byKey(
        const ValueKey<String>('travel-template-edit-title-field'),
      );
      final summaryField = find.byKey(
        const ValueKey<String>('travel-template-edit-summary-field'),
      );
      await tester.enterText(titleField, '西湖亲子周末');
      await tester.enterText(summaryField, '春秋季亲子同行');
      await tester.tap(
        find.byKey(const ValueKey<String>('travel-template-edit-confirm')),
      );
      await tester.pumpAndSettle();

      expect(facet.revision?.templateId, 'template-1');
      expect(facet.revision?.expectedVersion, 3);
      expect(facet.revision?.items, hasLength(1));
      expect(facet.revision?.attributions, hasLength(1));
      expect(facet.idempotencyKey, 'template-revise-intent-1');
      expect(find.text('西湖亲子周末'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pump(const Duration(seconds: 4));
    },
  );
}

final class _TemplateFacet implements TripTemplateFacet {
  TripPlanTemplate template = _template();
  PutTripPlanTemplateRequest? revision;
  String? idempotencyKey;

  @override
  Future<TripPlanTemplate> getTemplate(GetTripPlanTemplateQuery query) async {
    return template;
  }

  @override
  Future<TripPlanTemplate> createTemplate(
    CreateTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<TripPlanTemplateListSlice> listTemplates() async {
    return TripPlanTemplateListSlice(templates: <TripPlanTemplate>[template]);
  }

  @override
  Future<TripPlanTemplate> reviseTemplate(
    PutTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) async {
    revision = request;
    this.idempotencyKey = idempotencyKey;
    template = _template(
      version: request.expectedVersion + 1,
      title: request.title,
      summary: request.summary,
    );
    return template;
  }
}

TripPlanTemplate _template({
  int version = 3,
  String title = '西湖两日模板',
  String? summary = '适合朋友同行',
}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanTemplate(
    id: 'template-1',
    version: version,
    ownerPersonaId: 'persona-1',
    title: title,
    summary: summary,
    dayCount: 1,
    templateItemIds: const <String>['template-item-1'],
    items: const <TripPlanTemplateItem>[
      TripPlanTemplateItem(
        templateItemId: 'template-item-1',
        dayOffset: 0,
        orderInDay: 1,
        kind: 'sight',
        title: '西湖',
        attributionIds: <String>['source-1'],
      ),
    ],
    attributionIds: const <String>['source-1'],
    attributionPersonaIds: const <String>['persona-author'],
    attributions: const <TripPlanTemplateAttribution>[
      TripPlanTemplateAttribution(
        attributionId: 'source-1',
        kind: TripPlanTemplateAttributionKind.professionalCommentary,
        referenceObjectTypeRef: 'content.Post',
        referenceObjectId: 'post-1',
        authorPersonaId: 'persona-author',
        title: '领队讲解',
      ),
    ],
    status: TripPlanTemplateStatus.active,
    createdAt: now,
    updatedAt: now,
  );
}
