// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001.t1
// readiness_case: greeting_request_send_greeting_request_app_api
// readiness_case: greeting_request_list_greeting_inbox_app_api
// readiness_case: greeting_request_list_greeting_outbox_app_api
// readiness_case: greeting_request_reply_greeting_request_app_api
// readiness_case: greeting_request_ignore_greeting_request_app_api
// readiness_case: greeting_request_cancel_greeting_request_app_api

/// GreetingRequest production Remote API source contract.
///
/// Both participants are disposable anonymous accounts created by the public
/// account boundary. Every GreetingRequest precondition and cleanup action uses
/// a generated production Remote; there is no fixture, seed, or provider.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() => harness.close());

  test(
    'two disposable personas send, list, and replay a promoted greeting',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final requester = await harness.loginDisposableAccount(
        'greeting-requester-$suffix',
      );
      final target = await harness.loginDisposableAccount(
        'greeting-target-$suffix',
      );
      final requesterPersonaId = requester.activePersona!.personaId;
      final targetPersonaId = target.activePersona!.personaId;
      var requesterClosed = false;
      var targetClosed = false;

      addTearDown(() async {
        if (!targetClosed) {
          await harness.withSession(
            session: target,
            action: () => harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'greeting-target-cleanup-$suffix',
              ),
            ),
          );
        }
        if (!requesterClosed) {
          await harness.withSession(
            session: requester,
            action: () => harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'greeting-requester-cleanup-$suffix',
              ),
            ),
          );
        }
      });

      final relationshipBefore = await harness.withSession(
        session: requester,
        action: () => harness.personaRelationships.getRelationshipCapability(
          GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
        ),
      );
      expect(relationshipBefore.relationState, RelationshipState.notFollowing);

      final sendCommand = SendGreetingCommand(
        targetPersonaId: targetPersonaId,
        requestMessage: 'API contract greeting $suffix',
        source: 'profile',
      );
      final sendKey = 'greeting-send-$suffix';
      final sent = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: sendKey,
          action: () => harness.greetingRequests.sendGreeting(sendCommand),
        ),
      );
      final sendReplay = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: sendKey,
          action: () => harness.greetingRequests.sendGreeting(sendCommand),
        ),
      );
      expect(sent.id, isNotEmpty);
      expect(sent.status, GreetingRequestStatus.pending);
      expect(sent.requesterPersonaId, requesterPersonaId);
      expect(sent.targetPersonaId, targetPersonaId);
      expect(sendReplay.id, sent.id);
      expect(sendReplay.createdAt, sent.createdAt);

      final inbox = await harness.withSession(
        session: target,
        action: () => harness.greetingRequests.listGreetingInbox(
          ListGreetingRequestsQuery(status: 'pending', limit: 20),
        ),
      );
      expect(inbox.items.map((item) => item.id), contains(sent.id));

      final outbox = await harness.withSession(
        session: requester,
        action: () => harness.greetingRequests.listGreetingOutbox(
          ListGreetingRequestsQuery(status: 'pending', limit: 20),
        ),
      );
      expect(outbox.items.map((item) => item.id), contains(sent.id));

      final replyCommand = ReplyGreetingCommand(requestId: sent.id);
      final replyKey = 'greeting-reply-$suffix';
      final replied = await harness.withSession(
        session: target,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: replyKey,
          action: () => harness.greetingRequests.replyGreeting(replyCommand),
        ),
      );
      final replyReplay = await harness.withSession(
        session: target,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: replyKey,
          action: () => harness.greetingRequests.replyGreeting(replyCommand),
        ),
      );
      expect(replied.id, sent.id);
      expect(replied.status, GreetingRequestStatus.replied);
      expect(replied.promotedConversationId, isNotEmpty);
      expect(replyReplay.id, replied.id);
      expect(
        replyReplay.promotedConversationId,
        replied.promotedConversationId,
      );

      final ignoreCommand = SendGreetingCommand(
        targetPersonaId: targetPersonaId,
        requestMessage: 'API contract ignore $suffix',
        source: 'profile',
      );
      final ignoreSeed = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-ignore-seed-$suffix',
          action: () => harness.greetingRequests.sendGreeting(ignoreCommand),
        ),
      );
      final ignored = await harness.withSession(
        session: target,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-ignore-$suffix',
          action: () => harness.greetingRequests.ignoreGreeting(
            IgnoreGreetingCommand(requestId: ignoreSeed.id),
          ),
        ),
      );
      final ignoreReplay = await harness.withSession(
        session: target,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-ignore-$suffix',
          action: () => harness.greetingRequests.ignoreGreeting(
            IgnoreGreetingCommand(requestId: ignoreSeed.id),
          ),
        ),
      );
      expect(ignored.status, GreetingRequestStatus.ignored);
      expect(ignored.promotedConversationId, isNull);
      expect(ignoreReplay.id, ignored.id);
      expect(ignoreReplay.status, ignored.status);
      final ignoredReadback = await harness.withSession(
        session: target,
        action: () => _pollGreetingRequest(
          () => harness.greetingRequests.listGreetingInbox(
            const ListGreetingRequestsQuery(limit: 100),
          ),
          requestId: ignored.id,
          status: GreetingRequestStatus.ignored,
        ),
      );
      expect(ignoredReadback.promotedConversationId, isNull);

      final cancelCommand = SendGreetingCommand(
        targetPersonaId: targetPersonaId,
        requestMessage: 'API contract cancel $suffix',
        source: 'profile',
      );
      final cancelSeed = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-cancel-seed-$suffix',
          action: () => harness.greetingRequests.sendGreeting(cancelCommand),
        ),
      );
      final cancelled = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-cancel-$suffix',
          action: () => harness.greetingRequests.cancelGreeting(
            CancelGreetingCommand(requestId: cancelSeed.id),
          ),
        ),
      );
      final cancelReplay = await harness.withSession(
        session: requester,
        action: () => harness.withIdempotencyKey(
          idempotencyKey: 'greeting-cancel-$suffix',
          action: () => harness.greetingRequests.cancelGreeting(
            CancelGreetingCommand(requestId: cancelSeed.id),
          ),
        ),
      );
      expect(cancelled.status, GreetingRequestStatus.cancelled);
      expect(cancelled.promotedConversationId, isNull);
      expect(cancelReplay.id, cancelled.id);
      expect(cancelReplay.status, cancelled.status);
      final cancelledReadback = await harness.withSession(
        session: requester,
        action: () => _pollGreetingRequest(
          () => harness.greetingRequests.listGreetingOutbox(
            const ListGreetingRequestsQuery(limit: 100),
          ),
          requestId: cancelled.id,
          status: GreetingRequestStatus.cancelled,
        ),
      );
      expect(cancelledReadback.promotedConversationId, isNull);

      final relationshipAfter = await harness.withSession(
        session: requester,
        action: () => harness.personaRelationships.getRelationshipCapability(
          GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
        ),
      );
      expect(relationshipAfter.relationState, relationshipBefore.relationState);
      expect(relationshipAfter.hasFormalConversation, isTrue);

      final events = await harness.telemetry.waitForEvents(minimumCount: 9);
      final greetingEvents = events
          .where(
            (event) =>
                event.canonicalOperationId.startsWith('user.greeting_request.'),
          )
          .toList(growable: false);
      expect(greetingEvents, hasLength(6));
      expect(greetingEvents.every((event) => event.succeeded), isTrue);
      expect(
        greetingEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );

      await harness.withSession(
        session: target,
        action: () => harness.accountLifecycle.closeAccount(
          CloseAccountCommand(
            clientRequestId: 'greeting-target-cleanup-$suffix',
          ),
        ),
      );
      targetClosed = true;
      await harness.withSession(
        session: requester,
        action: () => harness.accountLifecycle.closeAccount(
          CloseAccountCommand(
            clientRequestId: 'greeting-requester-cleanup-$suffix',
          ),
        ),
      );
      requesterClosed = true;
    },
  );
}

Future<GreetingRequestRecord> _pollGreetingRequest(
  Future<GreetingRequestSlice> Function() read, {
  required String requestId,
  required GreetingRequestStatus status,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    final page = await read();
    for (final request in page.items) {
      if (request.id == requestId && request.status == status) {
        return request;
      }
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError(
        'Timed out waiting for GreetingRequest $requestId to become '
        '${status.wireName}',
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
