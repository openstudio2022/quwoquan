import 'package:quwoquan_app/service/user_service/relationship/subject_follow/application/public/subject_follow_writer.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef SubjectFollowInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Production-only adapter. It contains no paths, operation IDs, JSON maps,
/// actor headers, decoders or fallback behavior.
final class RemoteSubjectFollowFacet implements SubjectFollowWriter {
  const RemoteSubjectFollowFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SubjectFollowInvocationContextFactory invocationContext;

  @override
  Future<SubjectFollowCommandResult> follow(FollowSubjectCommand command) =>
      client.userSubjectFollowFollowSubject(
        command,
        context: invocationContext(UserRequestPageIds.followSubject),
      );

  @override
  Future<SubjectFollowCommandResult> unfollow(UnfollowSubjectCommand command) =>
      client.userSubjectFollowUnfollowSubject(
        command,
        context: invocationContext(UserRequestPageIds.unfollowSubject),
      );
}
