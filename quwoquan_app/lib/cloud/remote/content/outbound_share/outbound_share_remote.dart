import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentOutboundShareInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      CreateContentOutboundShareCommand command,
    );

/// Production adapter for the immutable OutboundShareFact append port.
/// Paths, operation IDs, request bodies and decoders remain generated ABI.
final class RemoteContentOutboundShareAppendWriter
    implements ContentOutboundShareAppendWriter {
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
