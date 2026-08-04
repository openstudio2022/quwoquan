// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/user/relationship/greeting_request/greeting_request_typed_double.dart';
import 'package:test/test.dart';

void main() {
  group('GreetingRequest typed contract', () {
    test('decoder 严格解析 canonical record', () {
      final record = decodeGreetingRequestRecord(<String, Object?>{
        'id': 'gr_001',
        'requesterPersonaId': 'user_a',
        'targetPersonaId': 'user_b',
        'requestMessage': '你好，很高兴认识你！',
        'status': 'pending',
        'source': 'profile',
        'promotedConversationId': null,
        'expireAt': '2026-07-23T08:00:00Z',
        'decisionAt': null,
        'createdAt': '2026-07-20T08:00:00Z',
        'updatedAt': '2026-07-20T08:00:00Z',
      });

      expect(record.id, 'gr_001');
      expect(record.requesterPersonaId, 'user_a');
      expect(record.targetPersonaId, 'user_b');
      expect(record.requestMessage, '你好，很高兴认识你！');
      expect(record.status, GreetingRequestStatus.pending);
      expect(record.expireAt, DateTime.utc(2026, 7, 23, 8));
    });

    test('decoder 缺失 required field 时 fail closed', () {
      expect(
        () => decodeGreetingRequestRecord(const <String, Object?>{}),
        throwsFormatException,
      );
    });

    test('send command 只输出 canonical typed body', () {
      final payload =
          encodeUserGreetingRequestSendGreetingRequestGeneratedRequest(
            SendGreetingCommand(
              targetPersonaId: 'user_b',
              requestMessage: ' 认识一下 ',
              source: ' profile ',
            ),
          );

      expect(payload.body, <String, Object?>{
        'targetPersonaId': 'user_b',
        'requestMessage': '认识一下',
        'source': 'profile',
      });
    });

    test('send command 只发送交集引用意图，不接受客户端展示文案', () {
      const intersectionRef = GreetingIntersectionRef(
        intersectionId: 'intersection_1',
        evidenceId: 'evidence_1',
        sourceRef: 'coVisitedEntity',
        objectTypeRef: 'user',
        objectId: 'user_b',
      );
      final payload =
          encodeUserGreetingRequestSendGreetingRequestGeneratedRequest(
            SendGreetingCommand(
              targetPersonaId: 'user_b',
              intersectionRef: intersectionRef,
            ),
          );

      final body = payload.body! as Map<String, Object?>;
      expect(body['intersectionRef'], intersectionRef.toWire());
      expect(
        (body['intersectionRef']! as Map<String, Object?>).keys,
        isNot(contains('primaryText')),
      );
    });
  });

  group('AlphaGreetingRequestFacet', () {
    late AlphaGreetingRequestFacet facet;

    setUp(() {
      facet = AlphaGreetingRequestFacet(
        seedInbox: <GreetingRequestRecord>[
          _greetingRecord(id: 'inbox-1', requester: 'user_a'),
        ],
        seedOutbox: <GreetingRequestRecord>[
          _greetingRecord(id: 'outbox-1', target: 'user_b'),
        ],
      );
    });

    test('send 后可从 typed outbox query 回读且 id 唯一', () async {
      final first = await facet.sendGreeting(
        SendGreetingCommand(targetPersonaId: 'user_x', requestMessage: '认识一下'),
      );
      final second = await facet.sendGreeting(
        SendGreetingCommand(targetPersonaId: 'user_y'),
      );
      final outbox = await facet.listGreetingOutbox(
        const ListGreetingRequestsQuery(status: 'pending', limit: 20),
      );

      expect(first.status, GreetingRequestStatus.pending);
      expect(first.requestMessage, '认识一下');
      expect(first.id, isNot(second.id));
      expect(
        outbox.items.map((item) => item.targetPersonaId),
        containsAll(<String>['user_x', 'user_y']),
      );
    });

    test('reply 与 ignore 推进 inbox 终态', () async {
      final replied = await facet.replyGreeting(
        ReplyGreetingCommand(requestId: 'inbox-1'),
      );
      expect(replied.status, GreetingRequestStatus.replied);
      expect(replied.promotedConversationId, isNotEmpty);

      final ignoreFacet = AlphaGreetingRequestFacet(
        seedInbox: <GreetingRequestRecord>[
          _greetingRecord(id: 'inbox-ignore', requester: 'user_c'),
        ],
      );
      final ignored = await ignoreFacet.ignoreGreeting(
        IgnoreGreetingCommand(requestId: 'inbox-ignore'),
      );
      expect(ignored.status, GreetingRequestStatus.ignored);
      expect(ignored.decisionAt, isNotNull);
    });

    test('cancel 后 pending 过滤消失、cancelled 过滤可见', () async {
      final cancelled = await facet.cancelGreeting(
        CancelGreetingCommand(requestId: 'outbox-1'),
      );
      final pending = await facet.listGreetingOutbox(
        const ListGreetingRequestsQuery(status: 'pending'),
      );
      final cancelledSlice = await facet.listGreetingOutbox(
        const ListGreetingRequestsQuery(status: 'cancelled'),
      );

      expect(cancelled.status, GreetingRequestStatus.cancelled);
      expect(pending.items, isEmpty);
      expect(cancelledSlice.items.single.id, 'outbox-1');
    });
  });
}

GreetingRequestRecord _greetingRecord({
  required String id,
  String requester = 'fixture_user_current',
  String target = 'fixture_user_current',
}) {
  final createdAt = DateTime.utc(2026, 7, 20, 8);
  return GreetingRequestRecord(
    id: id,
    requesterPersonaId: requester,
    targetPersonaId: target,
    requestMessage: 'fixture greeting',
    status: GreetingRequestStatus.pending,
    source: GreetingRequestSource.profile,
    createdAt: createdAt,
    updatedAt: createdAt,
  );
}
