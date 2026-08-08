// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001

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
