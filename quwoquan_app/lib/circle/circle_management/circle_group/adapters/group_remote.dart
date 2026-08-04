import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleGroupInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

final class RemoteCircleGroupFacet
    implements CircleGroupCommandWriter, CircleGroupQueryReader {
  const RemoteCircleGroupFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleGroupInvocationContextFactory invocationContext;

  @override
  Future<CircleGroupCommandResult> create(CreateCircleGroupCommand command) =>
      client.circleCircleGroupCreateCircleGroup(
        command,
        context: invocationContext(
          CircleRequestPageIds.createCircleGroup,
          command: true,
        ),
      );

  @override
  Future<CircleGroupCommandResult> update(UpdateCircleGroupCommand command) =>
      client.circleCircleGroupUpdateCircleGroup(
        command,
        context: invocationContext(
          CircleRequestPageIds.updateCircleGroup,
          command: true,
        ),
      );

  @override
  Future<CircleGroupCommandResult> archive(ArchiveCircleGroupCommand command) =>
      client.circleCircleGroupArchiveCircleGroup(
        command,
        context: invocationContext(
          CircleRequestPageIds.archiveCircleGroup,
          command: true,
        ),
      );

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) =>
      client.circleCircleGroupGetCircleGroup(
        query,
        context: invocationContext(
          CircleRequestPageIds.getCircleGroup,
          command: false,
        ),
      );

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) =>
      client.circleCircleGroupListCircleGroups(
        query,
        context: invocationContext(
          CircleRequestPageIds.listCircleGroups,
          command: false,
        ),
      );

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) =>
      client.circleCircleGroupSearchCircleGroups(
        query,
        context: invocationContext(
          CircleRequestPageIds.searchCircleGroups,
          command: false,
        ),
      );
}
