// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_template_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'template list uses generated owner and travelTemplates surface',
    () async {
      final executor = _TemplateExecutor();
      final facet = RemoteTripTemplateFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.listTemplates();

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanTemplateListTripPlanTemplates,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTemplates.id);
      expect(result.templates.single.id, 'template-1');
    },
  );

  test(
    'template create uses typed request, timeline surface and intent key',
    () async {
      final executor = _TemplateExecutor();
      final facet = RemoteTripTemplateFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.createTemplate(
        CreateTripPlanTemplateRequest(
          title: '西湖一日',
          dayCount: 1,
          items: const <TripPlanTemplateItem>[
            TripPlanTemplateItem(
              templateItemId: 'template-item-1',
              dayOffset: 0,
              orderInDay: 1,
              kind: 'sight',
              title: '西湖',
              attributionIds: <String>[],
            ),
          ],
          attributions: const <TripPlanTemplateAttribution>[],
        ),
        idempotencyKey: 'template-intent-1',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanTemplateCreateTripPlanTemplate,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'template-intent-1');
      expect(executor.body, containsPair('dayCount', 1));
      expect(result.id, 'template-1');
    },
  );

  test('template revision uses CAS request and templates surface', () async {
    final executor = _TemplateExecutor();
    final facet = RemoteTripTemplateFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await facet.reviseTemplate(
      PutTripPlanTemplateRequest(
        templateId: 'template-1',
        expectedVersion: 1,
        title: '西湖亲子周末',
        summary: '春秋季适用',
        dayCount: 1,
        items: const <TripPlanTemplateItem>[
          TripPlanTemplateItem(
            templateItemId: 'template-item-1',
            dayOffset: 0,
            orderInDay: 1,
            kind: 'sight',
            title: '西湖',
            attributionIds: <String>[],
          ),
        ],
        attributions: const <TripPlanTemplateAttribution>[],
      ),
      idempotencyKey: 'template-revise-intent-1',
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.travelTripPlanTemplateReviseTripPlanTemplate,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.travelTemplates.id);
    expect(executor.context?.idempotencyKey, 'template-revise-intent-1');
    expect(executor.pathParameters, containsPair('templateId', 'template-1'));
    expect(executor.body, containsPair('expectedVersion', 1));
    expect(result.id, 'template-1');
  });
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: idempotencyKey,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
  );
}

final class _TemplateExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Object? body;
  Map<String, String>? pathParameters;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final encoded = requestEncoder();
    body = encoded.body;
    pathParameters = encoded.pathParameters;
    return responseDecoder(
      operation.canonicalOperationId ==
              AppCloudOperationIds.travelTripPlanTemplateListTripPlanTemplates
          ? <String, Object?>{
              'templates': <Object?>[_templateWire()],
            }
          : _templateWire(),
    );
  }
}

Map<String, Object?> _templateWire() => <String, Object?>{
  'id': 'template-1',
  'version': 1,
  'ownerPersonaId': 'persona-1',
  'title': '西湖一日',
  'summary': '吃玩住行一体安排',
  'dayCount': 1,
  'templateItemIds': <Object?>['item-1'],
  'items': <Object?>[
    <String, Object?>{
      'templateItemId': 'item-1',
      'dayOffset': 0,
      'orderInDay': 1,
      'kind': 'sight',
      'title': '西湖',
      'attributionIds': <Object?>[],
    },
  ],
  'attributionIds': <Object?>[],
  'attributionPersonaIds': <Object?>[],
  'attributions': <Object?>[],
  'status': 'active',
  'createdAt': '2026-08-02T10:00:00Z',
  'updatedAt': '2026-08-02T10:00:00Z',
};
