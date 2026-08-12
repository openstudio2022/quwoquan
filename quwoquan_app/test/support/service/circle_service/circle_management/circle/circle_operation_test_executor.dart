import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// circle 各对象 generated ABI 契约测试共享的记录型 executor 与 wire fixture。
///
/// 原先与 circle_object_facets 测试同文件私有；按对象拆分后上收到 support，
/// 避免每个对象测试各自复制一份 wire 期望造成第二真相源。
Map<String, Object?> circleMembershipCommandResultFixture() =>
    <String, Object?>{
      'membershipId': 'membership-1',
      'version': 7,
      'state': 'active',
      'role': 'member',
      'idempotentReplay': false,
    };

Map<String, Object?> circleMembershipSliceFixture() => <String, Object?>{
  'membershipId': 'membership-1',
  'version': 7,
  'circleId': 'circle-1',
  'personaId': 'persona-1',
  'role': 'member',
  'state': 'active',
  'joinedAt': '2026-07-14T01:00:00Z',
  'leftAt': '0001-01-01T00:00:00Z',
  'lastActiveAt': '2026-07-14T01:00:00Z',
  'contribution': 0,
  'createdAt': '2026-07-14T01:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

Map<String, Object?> circleGroupCommandResultFixture() => <String, Object?>{
  'groupId': 'group-1',
  'version': 1,
  'status': 'active',
  'idempotentReplay': false,
};

Map<String, Object?> circleGroupSliceFixture() => <String, Object?>{
  'groupId': 'group-1',
  'version': 1,
  'circleId': 'circle-1',
  'groupType': 'self_built',
  'name': '远行同好',
  'visibility': 'private',
  'joinPolicy': 'apply_only',
  'storageEnabled': true,
  'noticeEnabled': false,
  'isDefaultPublicGroup': false,
  'status': 'active',
  'memberCount': 0,
  'createdAt': '2026-07-14T01:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

Map<String, Object?> circleGroupMembershipCommandResultFixture() =>
    <String, Object?>{
      'membershipId': 'group-membership-1',
      'version': 5,
      'role': 'member',
      'state': 'active',
      'idempotentReplay': false,
    };

Map<String, Object?> circleGroupMembershipSliceFixture() => <String, Object?>{
  'membershipId': 'group-membership-1',
  'version': 5,
  'groupId': 'group-1',
  'circleId': 'circle-1',
  'personaId': 'persona-2',
  'role': 'member',
  'state': 'active',
  'joinedAt': '2026-07-14T01:00:00Z',
  'leftAt': null,
  'decidedAt': '2026-07-14T01:00:00Z',
  'createdAt': '2026-07-14T00:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

final class CircleRecordingExecutor implements CloudOperationExecutor {
  CircleRecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
  Map<String, String> headers = const <String, String>{};
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
    headers = payload.headers;
    body = payload.body;
    return responseDecoder(response);
  }
}
