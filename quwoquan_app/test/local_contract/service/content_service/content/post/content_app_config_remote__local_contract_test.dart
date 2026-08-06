// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
// readiness_case: post_get_app_config_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_app_config_remote.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/test_content_app_config.dart';

void main() {
  test(
    'GetAppConfig 只经 generated operation client 解码 AppConfigSlice',
    () async {
      final executor = _RecordingExecutor();
      final query = RemoteContentAppConfigQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'homeFeed',
          routeId: 'home',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
      );

      final result = await query.getAppConfig();

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentPostGetAppConfig,
      );
      expect(
        executor.context?.clientPageId,
        ContentRequestPageIds.getAppConfig,
      );
      expect(executor.request?.body, isNull);
      expect(executor.request?.queryParameters, isEmpty);
      expect(result, isA<AppConfigSlice>());
      expect(result.content.grayRelease.experimentBucket, 'control');
    },
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? request;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    request = requestEncoder();
    return responseDecoder(testSignedAppConfigRoot());
  }
}
