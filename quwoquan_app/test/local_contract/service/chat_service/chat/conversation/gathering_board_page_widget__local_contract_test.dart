// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/gathering_board_page.dart';

final class _RecordingGatheringBoardQuery implements GatheringBoardQuery {
  _RecordingGatheringBoardQuery(this.snapshot);

  final GatheringBoardSnapshot snapshot;
  final List<GatheringBoardQueryRequest> requests =
      <GatheringBoardQueryRequest>[];

  @override
  Future<GatheringBoardSnapshot> load(
    GatheringBoardQueryRequest request,
  ) async {
    requests.add(request);
    return snapshot;
  }
}

GatheringBoardCapabilitySummary _available(String label, {int count = 0}) =>
    GatheringBoardCapabilitySummary(
      state: GatheringBoardCapabilityState.available,
      summaryLabel: label,
      itemCount: count,
    );

GatheringBoardCapabilitySummary _unavailable(
  String label,
  String unavailableLabel,
) => GatheringBoardCapabilitySummary(
  state: GatheringBoardCapabilityState.unavailable,
  summaryLabel: label,
  unavailableReason:
      GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
  unavailableLabel: unavailableLabel,
);

GatheringBoardSnapshot _snapshot({
  GatheringBoardAccessMode accessMode = GatheringBoardAccessMode.active,
  GatheringBoardCapabilitySummary? planCapability,
  GatheringBoardCapabilitySummary? mapCapability,
  GatheringBoardCapabilitySummary? calendarCapability,
}) {
  return GatheringBoardSnapshot(
    activity: GatheringBoardActivitySlice(
      gatheringId: 'gathering-1',
      title: '西湖日落摄影同行',
      scheduleLabel: '8 月 16 日 16:00–20:00',
      placeLabel: '西湖 · 北山街集合',
    ),
    participation: GatheringBoardParticipationSlice(
      activeCount: 6,
      maxParticipants: 8,
      remainingSeats: 2,
      summaryLabel: '6 位成员 · 剩余 2 个名额',
    ),
    plan: GatheringBoardPlanSlice(
      capability: planCapability ?? _available('路线与计划 · 2 项', count: 2),
      items: planCapability?.isAvailable == false
          ? const <GatheringBoardPlanItem>[]
          : const <GatheringBoardPlanItem>[
              GatheringBoardPlanItem(
                planItemId: 'plan-1',
                title: '北山街集合',
                detail: '16:00',
                completed: true,
              ),
              GatheringBoardPlanItem(
                planItemId: 'plan-2',
                title: '断桥日落机位',
                detail: '18:20',
                completed: false,
              ),
            ],
    ),
    chat: GatheringBoardChatSlice(
      access: GatheringBoardChatAccessSummary(
        gatheringId: 'gathering-1',
        conversationId: 'conversation-1',
        accessMode: accessMode,
        viewerRole: 'participant',
        canPost: accessMode == GatheringBoardAccessMode.active,
        statusLabel: accessMode == GatheringBoardAccessMode.active
            ? '可参与协作'
            : '活动已结束 · 只读',
      ),
      pinnedAnnouncement: GatheringBoardPinnedAnnouncement(
        content: '请带三脚架，集合后统一确认返程。',
        updatedBy: '组织者 林一',
        updatedAt: DateTime.utc(2026, 8, 10),
      ),
      assets: [
        GatheringBoardAssetIndexItem(
          messageId: 'message-image',
          mediaAssetId: 'asset-image',
          kind: GatheringBoardAssetKind.image,
          displayLabel: '集合点示意图',
          createdAt: DateTime.utc(2026, 8, 10),
        ),
        GatheringBoardAssetIndexItem(
          messageId: 'message-video',
          mediaAssetId: 'asset-video',
          kind: GatheringBoardAssetKind.video,
          displayLabel: '机位演示视频',
          createdAt: DateTime.utc(2026, 8, 10),
        ),
        GatheringBoardAssetIndexItem(
          messageId: 'message-file',
          mediaAssetId: 'asset-file',
          kind: GatheringBoardAssetKind.file,
          displayLabel: '活动须知.pdf',
          createdAt: DateTime.utc(2026, 8, 10),
        ),
      ],
    ),
    mapCapability: mapCapability ?? _available('地图路线可查看'),
    calendarCapability:
        calendarCapability ?? _available('日历与待办 · 2 项', count: 2),
  );
}

Future<void> _pumpBoard(
  WidgetTester tester, {
  required GatheringBoardQuery query,
  GatheringBoardNavigationCallbacks navigation =
      const GatheringBoardNavigationCallbacks(),
}) async {
  await tester.pumpWidget(
    CupertinoApp(
      home: GatheringBoardPage(
        conversationId: 'conversation-1',
        query: query,
        onBack: () {},
        navigation: navigation,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('active Board 读取 typed slice 并展示公告、计划、附件索引与名额', (tester) async {
    final query = _RecordingGatheringBoardQuery(_snapshot());
    var announcementOpened = 0;
    GatheringBoardNavigationTarget? announcementTarget;
    final openedAssets = <String>[];

    await _pumpBoard(
      tester,
      query: query,
      navigation: GatheringBoardNavigationCallbacks(
        openAnnouncement: (target) async {
          announcementOpened += 1;
          announcementTarget = target;
        },
        openAsset: (asset) async => openedAssets.add(asset.mediaAssetId),
      ),
    );

    expect(query.requests, hasLength(1));
    expect(query.requests.single.conversationId, 'conversation-1');
    expect(
      find.byKey(const ValueKey<String>('gathering-board-active')),
      findsOneWidget,
    );
    expect(find.text('请带三脚架，集合后统一确认返程。'), findsOneWidget);
    expect(find.text('北山街集合'), findsOneWidget);
    expect(find.text('6 位成员 · 剩余 2 个名额'), findsOneWidget);
    expect(find.text('集合点示意图'), findsOneWidget);
    expect(find.text('机位演示视频'), findsOneWidget);
    expect(find.text('活动须知.pdf'), findsOneWidget);

    final announcementSection = find.byKey(
      const ValueKey<String>('gathering-board-announcement'),
    );
    await tester.tap(
      find.descendant(
        of: announcementSection,
        matching: find.byIcon(CupertinoIcons.chevron_forward),
      ),
    );
    await tester.pump();
    expect(announcementOpened, 1);
    expect(announcementTarget?.gatheringId, 'gathering-1');
    expect(announcementTarget?.conversationId, 'conversation-1');

    await tester.tap(
      find.byKey(const ValueKey<String>('gathering-board-asset-asset-video')),
    );
    await tester.pump();
    expect(openedAssets, <String>['asset-video']);
  });

  testWidgets('read_only 明示只读但保留核心公告与附件', (tester) async {
    await _pumpBoard(
      tester,
      query: _RecordingGatheringBoardQuery(
        _snapshot(accessMode: GatheringBoardAccessMode.readOnly),
      ),
    );

    expect(
      find.byKey(const ValueKey<String>('gathering-board-read-only')),
      findsOneWidget,
    );
    expect(find.text('活动已结束 · 只读'), findsOneWidget);
    expect(find.text('请带三脚架，集合后统一确认返程。'), findsOneWidget);
    expect(find.text('集合点示意图'), findsOneWidget);
  });

  testWidgets('Plan、Map、Calendar 缺失时结构化降级且不隐藏公告', (tester) async {
    await _pumpBoard(
      tester,
      query: _RecordingGatheringBoardQuery(
        _snapshot(
          planCapability: _unavailable('路线与计划', '当前活动尚未启用计划'),
          mapCapability: _unavailable('地图', '当前设备暂不可打开地图'),
          calendarCapability: _unavailable('日历与待办', '当前设备没有可用日历'),
        ),
      ),
    );

    expect(find.text('当前活动尚未启用计划'), findsOneWidget);
    expect(find.text('当前设备暂不可打开地图'), findsOneWidget);
    expect(find.text('当前设备没有可用日历'), findsOneWidget);
    expect(
      find.byIcon(CupertinoIcons.exclamationmark_circle),
      findsNWidgets(3),
    );
    expect(find.text('请带三脚架，集合后统一确认返程。'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('gathering-board-assets')),
      findsOneWidget,
    );
  });
}
