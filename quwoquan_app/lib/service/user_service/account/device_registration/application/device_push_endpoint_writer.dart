import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';

/// `user/account/device_registration` 对象级写端口。
///
/// Remote adapter 只调用 generated operation client；本接口不接收 path / operationId。
abstract interface class DevicePushEndpointWriter {
  Future<void> upsert(DevicePushEndpoint endpoint);

  Future<void> remove(DevicePushEndpoint endpoint);
}

/// 登录后消费本地 token mutation；只有真实 writer 成功才从 queue 中 ack。
final class DevicePushEndpointCoordinator {
  DevicePushEndpointCoordinator({required this.gateway, required this.writer});

  final PushEndpointGateway gateway;
  final DevicePushEndpointWriter writer;

  Future<void>? _syncInFlight;

  Future<void> syncAfterLogin() {
    final active = _syncInFlight;
    if (active != null) {
      return active;
    }
    final task = _syncPending();
    _syncInFlight = task;
    return task.whenComplete(() {
      if (identical(_syncInFlight, task)) {
        _syncInFlight = null;
      }
    });
  }

  /// 必须在 auth credential 失效前调用；失败时 remove mutation 留在本地待下次登录。
  Future<void> removeForLogout() async {
    await gateway.queueActiveEndpointRemovals();
    await syncAfterLogin();
  }

  Future<void> _syncPending() async {
    final pending = await gateway.readPendingMutations();
    for (final mutation in pending) {
      switch (mutation.kind) {
        case PushEndpointMutationKind.upsert:
          await writer.upsert(mutation.endpoint);
        case PushEndpointMutationKind.remove:
          await writer.remove(mutation.endpoint);
      }
      await gateway.acknowledgeMutation(mutation.mutationId);
    }
  }
}
