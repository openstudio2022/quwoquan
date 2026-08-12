import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/research_release_readback.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/account_session_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ResearchReadbackInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Research readback 必须先由 User AccountSession 签发短期证明，再把 opaque
/// attestation 逐字节交给 generated Content header encoder。
final class RemoteResearchReleaseReadback implements ResearchReleaseReadback {
  const RemoteResearchReleaseReadback({
    required this.client,
    required this.researchIdentityWriter,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AccountSessionResearchIdentityWriter researchIdentityWriter;
  final ResearchReadbackInvocationContextFactory invocationContext;

  @override
  Future<ResearchReleaseReadbackView> readCurrentResearchRelease() async {
    final identity = await researchIdentityWriter.issueWhitelistedResearchSession(
      const IssueWhitelistedResearchSessionCommand(),
    );
    return client.contentPostGetResearchReleaseReadback(
      ResearchReleaseReadbackQuery(
        researchIdentityAttestation: identity.attestationId,
      ),
      context: invocationContext(
        ContentRequestPageIds.getResearchReleaseReadback,
      ),
    );
  }
}
