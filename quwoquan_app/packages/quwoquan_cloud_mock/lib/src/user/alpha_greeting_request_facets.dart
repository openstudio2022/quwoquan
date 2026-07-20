import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only 打招呼请求状态机；production 依赖图不可达。
final class AlphaGreetingRequestFacet
    implements GreetingRequestCommandWriter, GreetingRequestQuery {
  AlphaGreetingRequestFacet({
    this.requesterSubAccountId = 'fixture_user_current',
    Iterable<GreetingRequestRecord> seedInbox =
        const <GreetingRequestRecord>[],
    Iterable<GreetingRequestRecord> seedOutbox =
        const <GreetingRequestRecord>[],
  }) : _inbox = seedInbox.toList(growable: true),
       _outbox = seedOutbox.toList(growable: true);

  final String requesterSubAccountId;
  final List<GreetingRequestRecord> _inbox;
  final List<GreetingRequestRecord> _outbox;
  int _sequence = 0;

  @override
  Future<GreetingRequestRecord> sendGreeting(
    SendGreetingCommand command,
  ) async {
    final now = DateTime.now().toUtc();
    final record = GreetingRequestRecord(
      id: 'alpha-greeting-${++_sequence}',
      requesterSubAccountId: requesterSubAccountId,
      targetSubAccountId: command.targetSubAccountId,
      requestMessage: command.requestMessage,
      status: 'pending',
      source: command.source.trim().isEmpty ? 'profile' : command.source,
      createdAt: now,
      updatedAt: now,
    );
    _outbox.add(record);
    return record;
  }

  @override
  Future<GreetingRequestSlice> listGreetingInbox(
    ListGreetingRequestsQuery query,
  ) async => _slice(_inbox, query);

  @override
  Future<GreetingRequestSlice> listGreetingOutbox(
    ListGreetingRequestsQuery query,
  ) async => _slice(_outbox, query);

  @override
  Future<GreetingRequestRecord> replyGreeting(
    ReplyGreetingCommand command,
  ) async {
    return _transition(
      _inbox,
      command.requestId,
      status: 'replied',
      promotedConversationId: 'alpha-conversation-${command.requestId}',
    );
  }

  @override
  Future<GreetingRequestRecord> ignoreGreeting(
    IgnoreGreetingCommand command,
  ) async {
    return _transition(_inbox, command.requestId, status: 'ignored');
  }

  @override
  Future<GreetingRequestRecord> cancelGreeting(
    CancelGreetingCommand command,
  ) async {
    return _transition(_outbox, command.requestId, status: 'cancelled');
  }

  GreetingRequestSlice _slice(
    List<GreetingRequestRecord> source,
    ListGreetingRequestsQuery query,
  ) {
    final status = query.status.trim();
    final filtered = source
        .where((item) => status.isEmpty || item.status == status)
        .toList(growable: false);
    final start = int.tryParse(query.cursor?.trim() ?? '') ?? 0;
    final safeStart = start.clamp(0, filtered.length);
    final end = (safeStart + query.limit.clamp(1, 100)).clamp(
      0,
      filtered.length,
    );
    return GreetingRequestSlice(
      items: filtered.sublist(safeStart, end),
      nextCursor: end < filtered.length ? '$end' : null,
    );
  }

  GreetingRequestRecord _transition(
    List<GreetingRequestRecord> source,
    String requestId, {
    required String status,
    String? promotedConversationId,
  }) {
    final index = source.indexWhere((item) => item.id == requestId);
    if (index < 0) {
      throw StateError('greeting request not found');
    }
    final current = source[index];
    final now = DateTime.now().toUtc();
    final updated = GreetingRequestRecord(
      id: current.id,
      requesterSubAccountId: current.requesterSubAccountId,
      targetSubAccountId: current.targetSubAccountId,
      requestMessage: current.requestMessage,
      status: status,
      source: current.source,
      promotedConversationId:
          promotedConversationId ?? current.promotedConversationId,
      expireAt: current.expireAt,
      decisionAt: now,
      createdAt: current.createdAt,
      updatedAt: now,
    );
    source[index] = updated;
    return updated;
  }
}
