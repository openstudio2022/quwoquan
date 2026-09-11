import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 离线运行文档不授予网络能力；编码、鉴权与传输之前即明确拒绝。
///
/// 本执行器不返回业务数据，不是 Mock transport，也不持有远端 client。
final class UnavailableCloudOperationExecutor
    implements CloudOperationExecutor, CloudOperationStreamExecutor {
  const UnavailableCloudOperationExecutor();

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    throwIfCloudOperationInterrupted(
      cancellation: context.cancellation,
      deadlineAt: context.deadlineAt,
    );
    throw contentCapabilityUnavailable('remote_operation');
  }

  @override
  Stream<TResponse> stream<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async* {
    throwIfCloudOperationInterrupted(
      cancellation: context.cancellation,
      deadlineAt: context.deadlineAt,
    );
    throw contentCapabilityUnavailable('remote_stream');
  }
}
