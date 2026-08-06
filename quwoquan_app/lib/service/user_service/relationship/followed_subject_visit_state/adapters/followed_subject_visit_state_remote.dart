import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/application/public/followed_subject_visit_state_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef FollowedSubjectVisitStateInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteFollowedSubjectVisitStateWriter
    implements FollowedSubjectVisitStateWriter {
  const RemoteFollowedSubjectVisitStateWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final FollowedSubjectVisitStateInvocationContextFactory invocationContext;

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) {
    final requestId = command.clientRequestId?.trim() ?? '';
    return client.userFollowedSubjectVisitStateMarkFollowedSubjectVisited(
      command,
      context: invocationContext(
        UserRequestPageIds.markFollowedSubjectVisited,
        idempotencyKey: requestId.isEmpty ? null : requestId,
      ),
    );
  }
}
