import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/application/public/following_subject_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef FollowingSubjectInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteFollowingSubjectReader implements FollowingSubjectReader {
  const RemoteFollowingSubjectReader({
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
}
