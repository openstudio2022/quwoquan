import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CloudOperationResponseFactory =
    Object? Function(CloudOperationContract operation);

final class RecordedCloudOperationCall {
  const RecordedCloudOperationCall({
    required this.operation,
    required this.context,
    required this.payload,
  });

  final CloudOperationContract operation;
  final CloudOperationInvocationContext context;
  final CloudOperationRequestPayload payload;
}

/// Records generated-client calls while keeping production request encoders and
/// response decoders in the execution path.
final class CloudOperationRoutingRecorder implements CloudOperationExecutor {
  CloudOperationRoutingRecorder({required this.responseFor});

  final CloudOperationResponseFactory responseFor;
  final calls = <RecordedCloudOperationCall>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final payload = requestEncoder();
    calls.add(
      RecordedCloudOperationCall(
        operation: operation,
        context: context,
        payload: payload,
      ),
    );
    return responseDecoder(responseFor(operation));
  }
}
