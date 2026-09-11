import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
void main() {
  const executor = UnavailableCloudOperationExecutor();
  final operation =
      appCloudOperationContracts[AppCloudOperationIds
          .integrationLocationSearchLocations]!;
  const invocation = CloudOperationInvocationContext(
    surfaceId: 'createWorkspace',
    clientPageId: 'location-search',
    actor: CloudOperationActorContext(),
  );

  test('离线普通请求在编码与解码前拒绝，不伪造服务器结果', () async {
    var encoded = false;
    var decoded = false;
    await expectLater(
      executor.send<Object?>(
        operation,
        context: invocation,
        requestEncoder: () {
          encoded = true;
          throw StateError('request encoder must not run');
        },
        responseDecoder: (value) {
          decoded = true;
          return value;
        },
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.runtimeFailure.kind,
          'kind',
          RuntimeFailureKind.unsupported,
        ),
      ),
    );
    expect(encoded, isFalse);
    expect(decoded, isFalse);
  });

  test('离线流式请求不能启动网络或产出伪造事件', () async {
    var encoded = false;
    await expectLater(
      executor.stream<Object?>(
        operation,
        context: invocation,
        requestEncoder: () {
          encoded = true;
          throw StateError('request encoder must not run');
        },
        responseDecoder: (value) => value,
      ),
      emitsError(isA<CloudException>()),
    );
    expect(encoded, isFalse);
  });
}
