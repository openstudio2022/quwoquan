import 'package:quwoquan_app/service/assistant_service/assistant/page_context/adapters/assistant_open_context_mapper.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/page_context_command_writer.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef PageContextInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// PageContext generated-client command adapter。
final class PageContextGeneratedAdapter implements PageContextCommandWriter {
  const PageContextGeneratedAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final PageContextInvocationContextFactory invocationContext;

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    final receipt = await client.assistantPageContextReportPageContext(
      ReportPageContextCommand(
        contextSnapshot: pageContextSnapshotFromOpenContext(
          context,
          userAction: userAction,
        ),
      ),
      context: invocationContext(
        AssistantRequestPageIds.reportPageContext,
        networkSurface: false,
      ),
    );
    if (!receipt.accepted) {
      throw const FormatException('page context was not accepted');
    }
    return receipt;
  }
}
