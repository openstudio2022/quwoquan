import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test('alpha profile interaction 分页与 read fact 单调幂等', () async {
    var now = DateTime.utc(2026, 7, 20, 3);
    final facet = AlphaProfileInteractionFacet(clock: () => now);
    final query = ContentProfileInteractionPageQuery(
      subAccountId: 'fixture_user_current',
      type: ContentProfileInteractionType.share,
      limit: 2,
    );

    final first = await facet.listActivities(
      query,
      direction: ContentProfileInteractionDirection.received,
    );
    expect(first.items, hasLength(2));
    expect(first.hasMore, isTrue);
    expect(first.nextCursor, isNotEmpty);
    final activityID = first.items.first.activityId;

    final read = await facet.appendReadFact(
      AppendContentProfileInteractionReadFactCommand(
        subAccountId: 'fixture_user_current',
        activityId: activityID,
        state: ContentProfileInteractionReadState.read,
      ),
    );
    final replay = await facet.appendReadFact(
      AppendContentProfileInteractionReadFactCommand(
        subAccountId: 'fixture_user_current',
        activityId: activityID,
        state: ContentProfileInteractionReadState.read,
      ),
    );
    expect(replay.factId, read.factId);
    expect(replay.replayed, isTrue);

    now = now.add(const Duration(minutes: 1));
    await facet.appendReadFact(
      AppendContentProfileInteractionReadFactCommand(
        subAccountId: 'fixture_user_current',
        activityId: activityID,
        state: ContentProfileInteractionReadState.seen,
      ),
    );
    final refreshed = await facet.listActivities(
      query,
      direction: ContentProfileInteractionDirection.received,
    );
    final item = refreshed.items.singleWhere(
      (candidate) => candidate.activityId == activityID,
    );
    expect(item.seenAt, isNotNull);
    expect(item.readAt, read.occurredAt);

    final second = await facet.listActivities(
      ContentProfileInteractionPageQuery(
        subAccountId: 'fixture_user_current',
        type: ContentProfileInteractionType.share,
        cursor: first.nextCursor,
        limit: 2,
      ),
      direction: ContentProfileInteractionDirection.received,
    );
    expect(
      second.items.map((item) => item.activityId).toSet().intersection(
        first.items.map((item) => item.activityId).toSet(),
      ),
      isEmpty,
    );
  });
}
