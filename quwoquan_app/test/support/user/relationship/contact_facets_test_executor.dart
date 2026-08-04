import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// user.relationship 各对象 generated client 契约测试共享的记录型 executor
/// 与 wire fixture。
///
/// 原先与 contact_facets_generated_client 测试同文件私有；按对象拆分后上收，
/// 避免三个对象各自复制一份 wire 期望造成第二真相源。
Map<String, Object?> greetingRequestRecordFixture({required String status}) {
  return <String, Object?>{
    'id': 'greeting-1',
    'requesterPersonaId': 'persona-current',
    'targetPersonaId': 'persona-target',
    'requestMessage': '你好',
    'status': status,
    'source': 'profile',
    'createdAt': '2026-07-20T00:00:00Z',
    'updatedAt': '2026-07-20T00:00:00Z',
  };
}

final class ContactRecordingExecutor implements CloudOperationExecutor {
  ContactRecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
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
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
