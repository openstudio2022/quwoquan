import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef FollowingSubjectInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  const RemoteFollowingSubjectFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final FollowingSubjectInvocationContextFactory invocationContext;

  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) {
    return client.userFollowingSubjectListFollowingSubjects(
      query,
      context: invocationContext(UserRequestPageIds.listFollowingSubjects),
    );
  }

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) {
    return client.userFollowedSubjectVisitStateMarkFollowedSubjectVisited(
      command,
      context: invocationContext(UserRequestPageIds.markFollowedSubjectVisited),
    );
  }
}
