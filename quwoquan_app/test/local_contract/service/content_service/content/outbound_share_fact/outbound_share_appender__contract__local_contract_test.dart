// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/adapters/outbound_share_remote.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/outbound_share_fact/outbound_share_writer_typed_double.dart';

CreateContentOutboundShareCommand _command(String referralId) =>
    CreateContentOutboundShareCommand(
      postId: 'post-outbound-share-contract',
      channel: OutboundShareChannel.systemShare,
      destinationKind: OutboundShareDestinationKind.externalApp,
      destination: 'system-share-sheet',
      referralId: referralId,
      providerReceiptId: 'receipt-$referralId',
      clientConfirmedAt: DateTime.utc(2026, 8, 5, 8),
    );

void main() {
  test(
    'production Remote binds the generated operation and page context',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'eventId': 'share-event-remote',
          'postId': 'post-outbound-share-contract',
          'channel': 'system_share',
          'referralId': 'referral-remote',
          'occurredAt': '2026-08-05T08:00:00Z',
          'replayed': false,
        },
      );
      final contextCommands = <CreateContentOutboundShareCommand>[];
      final writer = RemoteContentOutboundShareAppendWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, command) {
          expect(clientPageId, ContentRequestPageIds.appendOutboundShareFact);
          contextCommands.add(command);
          return CloudOperationInvocationContext(
            surfaceId: 'workBrowser',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            idempotencyKey: command.referralId,
          );
        },
      );
      final command = _command('referral-remote');

      final result = await writer.appendOutboundShare(command);

      expect(contextCommands, <CreateContentOutboundShareCommand>[command]);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentOutboundShareFactAppendOutboundShareFact,
      );
      expect(executor.context?.idempotencyKey, 'referral-remote');
      expect(executor.pathParameters, <String, String>{
        'postId': 'post-outbound-share-contract',
      });
      expect(result.eventId, 'share-event-remote');
    },
  );

  test('公开 appender 以 referralId 幂等记录确认后的分享事实', () async {
    final ContentOutboundShareAppender appender =
        ContentOutboundShareWriterTypedDouble();

    final first = await appender.appendOutboundShare(_command('referral-1'));
    final replay = await appender.appendOutboundShare(_command('referral-1'));
    final next = await appender.appendOutboundShare(_command('referral-2'));

    expect(first.replayed, isFalse);
    expect(replay.replayed, isTrue);
    expect(replay.eventId, first.eventId);
    expect(next.eventId, isNot(first.eventId));
    expect(next.referralId, 'referral-2');
  });
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final request = requestEncoder();
    pathParameters = request.pathParameters;
    return responseDecoder(response);
  }
}
