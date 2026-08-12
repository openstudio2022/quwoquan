// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-002
// readiness_case: homepage_claim_request_create_homepage_claim_request_app_local
// readiness_case: homepage_claim_request_get_my_pending_homepage_claim_request_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/adapters/homepage_claim_request_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('认领 Remote 映射本地 Draft 并执行唯一 generated operation', () async {
    final executor = _RecordingExecutor(response: _claimResponse());
    final writer = RemoteHomepageClaimRequestWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await writer.createClaimRequest(
      homepageId: 'homepage-1',
      clientRequestId: 'claim-intent-1',
      draft: HomepageClaimRequestDraft(
        claimTier: 'verified',
        contactPhone: '13800000000',
        businessLicenseUrl: 'https://media.example/license',
        identityCardFrontUrl: 'https://media.example/front',
        identityCardBackUrl: 'https://media.example/back',
        note: 'canonical claim',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.entityHomepageClaimRequestCreateHomepageClaimRequest,
    );
    expect(executor.pathParameters, <String, String>{
      'homepageId': 'homepage-1',
    });
    expect(executor.body, <String, Object?>{
      'claimTier': 'verified',
      'businessLicenseUrl': 'https://media.example/license',
      'contactPhone': '13800000000',
      'identityCardFrontUrl': 'https://media.example/front',
      'identityCardBackUrl': 'https://media.example/back',
      'note': 'canonical claim',
    });
    expect(
      executor.context?.clientPageId,
      EntityRequestPageIds.createHomepageClaimRequest,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.homepageClaim.id);
    expect(executor.context?.routeId, AppUiSurfaces.homepageClaim.routeId);
    expect(executor.context?.idempotencyKey, 'claim-intent-1');
    expect(result.claimRequestId, 'claim-1');
    expect(result.claimTier, HomepageClaimTier.verified);
    expect(result.status, HomepageClaimReviewStatus.pendingReview);
  });

  test('认领 Remote 对非 canonical 结果 fail closed', () async {
    final writer = RemoteHomepageClaimRequestWriter(
      client: GeneratedCloudOperationClient(
        _RecordingExecutor(response: <String, Object?>{'id': 'claim-1'}),
      ),
      invocationContext: _context,
    );

    await expectLater(
      writer.createClaimRequest(
        homepageId: 'homepage-1',
        draft: HomepageClaimRequestDraft(
          claimTier: 'basic',
          contactPhone: '13800000000',
        ),
      ),
      throwsFormatException,
    );
  });

  test('本人待审认领 Remote 执行 canonical GET 并 typed decode', () async {
    final executor = _RecordingExecutor(response: _claimResponse());
    final reader = RemoteHomepageClaimRequestReader(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _queryContext,
    );

    final result = await reader.getMyPendingClaimRequest(
      homepageId: 'homepage-1',
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds
          .entityHomepageClaimRequestGetMyPendingHomepageClaimRequest,
    );
    expect(executor.operation?.method, 'GET');
    expect(
      executor.operation?.pathTemplate,
      '/homepages/{homepageId}/claim-requests/mine',
    );
    expect(executor.pathParameters, <String, String>{
      'homepageId': 'homepage-1',
    });
    expect(executor.queryParameters, isEmpty);
    expect(
      executor.context?.clientPageId,
      EntityRequestPageIds.getMyPendingHomepageClaimRequest,
    );
    expect(executor.context?.idempotencyKey, isNull);
    expect(result.claimRequestId, 'claim-1');
    expect(result.requesterPersonaId, 'persona-1');
    expect(result.status, HomepageClaimReviewStatus.pendingReview);
  });
}

CloudOperationInvocationContext _context(
  String clientPageId,
  AppUiSurface surface, {
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
  idempotencyKey: idempotencyKey ?? 'claim-intent-fallback',
);

CloudOperationInvocationContext _queryContext(
  String clientPageId,
  AppUiSurface surface, {
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
);

Map<String, Object?> _claimResponse() => <String, Object?>{
  'claimRequestId': 'claim-1',
  'homepageId': 'homepage-1',
  'requesterPersonaId': 'persona-1',
  'claimTier': 'verified',
  'status': 'pending_review',
  'createdAt': '2026-08-05T00:00:00Z',
};

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
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
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
