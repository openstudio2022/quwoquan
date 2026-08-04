// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/adapters/trip_plan_directory_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('trip directory uses one typed owner-scoped keyset query', () async {
    final executor = _DirectoryExecutor();
    final directory = RemoteTripPlanDirectory(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final page = await directory.list(
      status: TripPlanStatus.active,
      cursor: 'cursor-1',
      limit: 12,
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.travelTripPlanListTripPlans,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.travelTrips.id);
    expect(executor.queryParameters, <String, String>{
      'status': 'active',
      'cursor': 'cursor-1',
      'limit': '12',
    });
    expect(executor.pathParameters, isEmpty);
    expect(executor.body, isNull);
    expect(page.plans.single.tripId, 'trip-1');
    expect(page.nextCursor, 'cursor-2');
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

final class _DirectoryExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> queryParameters = const <String, String>{};
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
    final request = requestEncoder();
    queryParameters = request.queryParameters;
    pathParameters = request.pathParameters;
    body = request.body;
    return responseDecoder(<String, Object?>{
      'plans': <Object?>[
        <String, Object?>{
          'tripId': 'trip-1',
          'title': '西湖同行',
          'status': 'active',
          'currentRevisionId': 'revision-2',
          'currentRevisionNumber': 2,
          'itemCount': 8,
          'updatedAt': '2026-08-02T10:00:00Z',
        },
      ],
      'nextCursor': 'cursor-2',
    });
  }
}
