// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_journey_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'timeline query uses canonical typed operation and travel surface',
    () async {
      final executor = _RecordingExecutor(response: _timelineWire());
      final query = RemoteTripJourneyQuery(
        client: GeneratedCloudOperationClient(executor),
        surface: AppUiSurfaces.travelTimeline,
        invocationContext: _context,
      );

      final timeline = await query.getTimeline('trip-1');

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripTimelineViewGetTripTimeline,
      );
      expect(executor.operation?.method, 'GET');
      expect(executor.pathParameters, <String, String>{'tripId': 'trip-1'});
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(timeline.currentRevisionNumber, 3);
      expect(timeline.days.single.items.single.title, '西湖晨游');
    },
  );

  test('map query never accepts a raw provider URL', () async {
    final executor = _RecordingExecutor(response: _mapWire());
    final query = RemoteTripJourneyQuery(
      client: GeneratedCloudOperationClient(executor),
      surface: AppUiSurfaces.travelMap,
      invocationContext: _context,
    );

    final map = await query.getMap('trip-1');

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.travelTripMapViewGetTripMap,
    );
    expect(executor.pathParameters, <String, String>{'tripId': 'trip-1'});
    expect(executor.body, isNull);
    expect(map.stops.single.placeRef.objectId, 'place-west-lake');
  });
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId,
) {
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}

Map<String, Object?> _timelineWire() => <String, Object?>{
  'tripId': 'trip-1',
  'tripVersion': 4,
  'tripStatus': 'active',
  'currentRevisionId': 'revision-3',
  'currentRevisionNumber': 3,
  'revisionChangeReason': '天气变化后调整',
  'revisionSeverity': 'minor',
  'tripContentLinks': <Object?>[],
  'days': <Object?>[
    <String, Object?>{
      'dayIndex': 1,
      'unassignedMoments': <Object?>[],
      'unassignedContentLinks': <Object?>[],
      'items': <Object?>[
        <String, Object?>{
          'itemId': 'item-1',
          'orderInDay': 1,
          'kind': 'sight',
          'title': '西湖晨游',
          'startAt': '2026-08-08T00:00:00Z',
          'endAt': '2026-08-08T02:00:00Z',
          'placeRef': <String, Object?>{
            'objectTypeRef': 'entity.Place',
            'objectId': 'place-west-lake',
          },
          'note': '避开午后高温',
          'moments': <Object?>[],
          'contentLinks': <Object?>[],
        },
      ],
    },
  ],
  'sourceMomentIds': <Object?>[],
  'sourceContentLinkIds': <Object?>[],
  'sourceDigest':
      'sha256:94d192b3a326be1f019b71ef13ea5a367ffe939c5e9a88f1b270e53753d9569a',
  'sourceEventId': 'event-timeline-1',
  'projectedAt': '2026-08-02T10:00:00Z',
};

Map<String, Object?> _mapWire() => <String, Object?>{
  'tripId': 'trip-1',
  'currentRevisionId': 'revision-3',
  'currentRevisionNumber': 3,
  'stops': <Object?>[
    <String, Object?>{
      'stopId': 'stop-1',
      'sequence': 1,
      'dayIndex': 1,
      'itemId': 'item-1',
      'title': '西湖晨游',
      'placeRef': <String, Object?>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'place-west-lake',
      },
      'momentIds': <Object?>[],
      'contentLinkIds': <Object?>[],
    },
  ],
  'routeSegments': <Object?>[],
  'momentMarkers': <Object?>[],
  'sourceMomentIds': <Object?>[],
  'sourceContentLinkIds': <Object?>[],
  'sourceDigest':
      'sha256:60be9861750facbfad8758254a2f76c0cfe78d54459a3bc187d49b1401fcd8e8',
  'sourceEventId': 'event-map-1',
  'projectedAt': '2026-08-02T10:00:00Z',
};
