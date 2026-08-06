import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentOutboundShareInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      CreateContentOutboundShareCommand command,
    );

/// Production adapter for the immutable OutboundShareFact append port.
/// Paths, operation IDs, request bodies and decoders remain generated ABI.
final class RemoteContentOutboundShareAppendWriter
    implements ContentOutboundShareAppender {
  const RemoteContentOutboundShareAppendWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentOutboundShareInvocationContextFactory invocationContext;

  @override
  Future<OutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  ) => client.contentOutboundShareFactCreateOutboundShare(
    command,
    context: invocationContext(
      ContentRequestPageIds.createOutboundShare,
      command,
    ),
  );
}
