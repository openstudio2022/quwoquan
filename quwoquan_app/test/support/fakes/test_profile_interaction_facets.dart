import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ProfileInteraction 查询与已读事实写面的 test-only 强类型替身。
final class TestProfileInteractionFacets
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  const TestProfileInteractionFacets({
    this.items = const <ContentProfileInteractionActivity>[],
  });

  final List<ContentProfileInteractionActivity> items;

  @override
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  }) async {
    return ContentProfileInteractionPage(
      items: items.take(query.limit).toList(growable: false),
    );
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    return ProfileInteractionReadFactAck(
      factId: 'test-fact-${command.activityId}',
      activityId: command.activityId,
      state: command.state.wireValue,
      occurredAt: DateTime.utc(2026, 7, 20),
      replayed: false,
    );
  }
}
