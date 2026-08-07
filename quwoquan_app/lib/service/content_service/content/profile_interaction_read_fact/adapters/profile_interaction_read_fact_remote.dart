import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_read_fact/application/profile_interaction_read_fact_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileInteractionReadFactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// ProfileInteractionReadFact 对象拥有的 generated append adapter。
final class RemoteProfileInteractionReadFactWriter
    implements ProfileInteractionReadFactWriter {
  const RemoteProfileInteractionReadFactWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ProfileInteractionReadFactInvocationContextFactory invocationContext;

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) {
    final base = invocationContext(
      ContentRequestPageIds.appendProfileInteractionReadFact,
    );
    return client.contentProfileInteractionReadFactAppendProfileInteractionReadFact(
      command,
      context: CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        actor: base.actor,
        routeId: base.routeId,
        referralSource: base.referralSource,
        feedRequestId: base.feedRequestId,
        shareId: base.shareId,
        modelId: base.modelId,
        experimentBucket: base.experimentBucket,
        deadlineAt: base.deadlineAt,
        cancellation: base.cancellation,
        idempotencyKey:
            'profile-read:${command.personaId}:${command.activityId}:${command.state.wireName}',
      ),
    );
  }
}
