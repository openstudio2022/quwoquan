import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha 环境的 Circle 聚合生命周期命令 fixture 适配器。
/// 语义与远端一致：actor 维度幂等重放、归档 no-op 返回原版本回执。
final class AlphaCircleLifecycleFacet
    implements CircleLifecycleCommandWriter, CircleConfigurationCommandWriter {
  final Map<String, CircleCommandResult> _byIdempotentIntent =
      <String, CircleCommandResult>{};
  final Map<String, CircleCommandResult> _circles =
      <String, CircleCommandResult>{};

  @override
  Future<CircleCommandResult> createCircle(CreateCircleCommand command) async {
    final intentKey = 'create:${command.name}';
    final existing = _byIdempotentIntent[intentKey];
    if (existing != null) {
      return _replayOf(existing);
    }
    final result = CircleCommandResult(
      circleId: 'alpha_circle_${_circles.length + 1}',
      version: 1,
      status: CircleLifecycleStatus.active,
      idempotentReplay: false,
    );
    _byIdempotentIntent[intentKey] = result;
    _circles[result.circleId] = result;
    return result;
  }

  @override
  Future<CircleCommandResult> updateCircle(UpdateCircleCommand command) async {
    return _advance(command.circleId, CircleLifecycleStatus.active);
  }

  @override
  Future<CircleCommandResult> archiveCircle(
    ArchiveCircleCommand command,
  ) async {
    final current = _circles[command.circleId];
    if (current != null && current.status == CircleLifecycleStatus.archived) {
      return _replayOf(current);
    }
    return _advance(command.circleId, CircleLifecycleStatus.archived);
  }

  @override
  Future<CircleCommandResult> updateCircleSections(
    UpdateCircleSectionsCommand command,
  ) async {
    return _advance(command.circleId, CircleLifecycleStatus.active);
  }

  CircleCommandResult _advance(String circleId, CircleLifecycleStatus status) {
    final current = _circles[circleId];
    final next = CircleCommandResult(
      circleId: circleId,
      version: (current?.version ?? 0) + 1,
      status: status,
      idempotentReplay: false,
    );
    _circles[circleId] = next;
    return next;
  }

  CircleCommandResult _replayOf(CircleCommandResult existing) {
    return CircleCommandResult(
      circleId: existing.circleId,
      version: existing.version,
      status: existing.status,
      idempotentReplay: true,
    );
  }
}
