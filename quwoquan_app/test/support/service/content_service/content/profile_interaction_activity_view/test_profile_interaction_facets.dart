import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ProfileInteraction 查询与已读事实写面的 test-only 强类型替身。
final class TestProfileInteractionFacets
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  const TestProfileInteractionFacets({
    this.items = const <ProfileInteractionActivityView>[],
  });

  final List<ProfileInteractionActivityView> items;

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) async {
    return ProfileInteractionActivityPageSlice(
      items: items.take(query.limit).toList(growable: false),
      nextCursor: null,
      hasMore: false,
    );
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    return ProfileInteractionReadFactAck(
      factId: 'test-fact-${command.activityId}',
      activityId: command.activityId,
      state: command.state,
      occurredAt: DateTime.utc(2026, 7, 20),
      replayed: false,
    );
  }
}
