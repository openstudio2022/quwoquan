import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleFileInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Production CircleFile adapter. Paths, operation IDs, codecs, retry and
/// error semantics are owned by the generated operation client.
final class RemoteCircleFileFacet
    implements CircleFileCommandWriter, CircleFileQueryReader {
  const RemoteCircleFileFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleFileInvocationContextFactory invocationContext;

  @override
  Future<CircleFileCommandResult> create(CreateCircleFileCommand command) =>
      client.circleCircleFileCreateCircleFile(
        command,
        context: invocationContext(
          CircleRequestPageIds.createCircleFile,
          command: true,
        ),
      );

  @override
  Future<CircleFileCommandResult> update(UpdateCircleFileCommand command) =>
      client.circleCircleFileUpdateCircleFile(
        command,
        context: invocationContext(
          CircleRequestPageIds.updateCircleFile,
          command: true,
        ),
      );

  @override
  Future<CircleFileCommandResult> delete(DeleteCircleFileCommand command) =>
      client.circleCircleFileDeleteCircleFile(
        command,
        context: invocationContext(
          CircleRequestPageIds.deleteCircleFile,
          command: true,
        ),
      );

  @override
  Future<CircleFileSlice> get(CircleFileQuery query) =>
      client.circleCircleFileGetCircleFile(
        query,
        context: invocationContext(
          CircleRequestPageIds.getCircleFile,
          command: false,
        ),
      );

  @override
  Future<CircleFilePageSlice> list(CircleFileListQuery query) =>
      client.circleCircleFileListCircleFiles(
        query,
        context: invocationContext(
          CircleRequestPageIds.listCircleFiles,
          command: false,
        ),
      );
}
