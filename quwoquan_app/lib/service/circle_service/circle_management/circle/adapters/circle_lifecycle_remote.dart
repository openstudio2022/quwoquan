import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleLifecycleInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Circle 聚合本体生命周期与板块配置命令的唯一远端适配器。
/// 命名状态迁移由服务端内部 version CAS 保护，命令不携带调用方版本字段；
/// Idempotency-Key 经 OperationInvocationContext 注入。
final class RemoteCircleLifecycleFacet
    implements CircleLifecycleCommandWriter, CircleConfigurationCommandWriter {
  const RemoteCircleLifecycleFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleLifecycleInvocationContextFactory invocationContext;

  @override
  Future<CircleCommandResult> createCircle(CreateCircleCommand command) =>
      client.circleCircleCreateCircle(
        command,
        context: invocationContext(
          CircleRequestPageIds.createCircle,
          command: true,
        ),
      );

  @override
  Future<CircleCommandResult> updateCircle(UpdateCircleCommand command) =>
      client.circleCircleUpdateCircle(
        command,
        context: invocationContext(
          CircleRequestPageIds.updateCircle,
          command: true,
        ),
      );

  @override
  Future<CircleCommandResult> archiveCircle(ArchiveCircleCommand command) =>
      client.circleCircleArchiveCircle(
        command,
        context: invocationContext(
          CircleRequestPageIds.archiveCircle,
          command: true,
        ),
      );

  @override
  Future<CircleCommandResult> updateCircleSections(
    UpdateCircleSectionsCommand command,
  ) => client.circleCircleUpdateCircleSections(
    command,
    context: invocationContext(
      CircleRequestPageIds.updateCircleSections,
      command: true,
    ),
  );
}
