// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/group-call/spec.md#gwt-001
//
// 视频网格动态重排契约（收口 call-experience OPEN-002）：
// 参与者加入/离开时，同一网格 widget 的列数与宽高比必须按人数档位
// 迁移（2 人 1 列 → 3-4 人 2 列 → 5-6 人 2 列方格 → 7-9 人 3 列）；
// activeSpeaker 高亮必须随说话人切换（当前实现为高亮标记，无 tile 重排）。
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/participant_tile.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/video_grid_layout.dart';

List<CallParticipantViewData> _participants(int count) {
  return List.generate(
    count,
    (i) => CallParticipantViewData(
      userId: 'user_$i',
      displayName: 'User $i',
      role: i == 0 ? ParticipantRole.initiator : ParticipantRole.invitee,
      status: ParticipantStatus.connected,
      isMuted: false,
      isCameraOn: false,
    ),
  );
}

Widget _grid({required int count, String? activeSpeakerId}) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 400,
          height: 600,
          child: VideoGridLayout(
            participants: _participants(count),
            activeSpeakerId: activeSpeakerId,
          ),
        ),
      ),
    ),
  );
}

int _crossAxisCount(WidgetTester tester) {
  final grid = tester.widget<GridView>(find.byType(GridView));
  final delegate =
      grid.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount;
  return delegate.crossAxisCount;
}

void main() {
  testWidgets('同一网格随 2→4→6→9 人动态迁移列数与宽高比', (tester) async {
    await tester.pumpWidget(_grid(count: 2));
    await tester.pump();
    expect(_crossAxisCount(tester), 1, reason: '2 人单列上下分屏');
    expect(find.byType(ParticipantTile), findsNWidgets(2));

    // 参与者加入：同一 widget 树上 pump 新人数，断言重排而非重建页面。
    await tester.pumpWidget(_grid(count: 4));
    await tester.pump();
    expect(_crossAxisCount(tester), 2, reason: '3-4 人 2 列');
    expect(find.byType(ParticipantTile), findsNWidgets(4));

    await tester.pumpWidget(_grid(count: 6));
    await tester.pump();
    expect(_crossAxisCount(tester), 2, reason: '5-6 人保持 2 列方格');
    final grid6 = tester.widget<GridView>(find.byType(GridView));
    final delegate6 =
        grid6.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount;
    expect(delegate6.childAspectRatio, 1.0, reason: '5-6 人档位切换为方形 tile');
    expect(find.byType(ParticipantTile), findsNWidgets(6));

    await tester.pumpWidget(_grid(count: 9));
    await tester.pump();
    expect(_crossAxisCount(tester), 3, reason: '7-9 人 3 列');

    // 参与者离开：回落档位。
    await tester.pumpWidget(_grid(count: 3));
    await tester.pump();
    expect(_crossAxisCount(tester), 2, reason: '回落到 3-4 人档位 2 列');
    expect(find.byType(ParticipantTile), findsNWidgets(3));
  });

  testWidgets('activeSpeaker 高亮随说话人切换', (tester) async {
    await tester.pumpWidget(_grid(count: 4, activeSpeakerId: 'user_1'));
    await tester.pump();

    Iterable<ParticipantTile> tiles() =>
        tester.widgetList<ParticipantTile>(find.byType(ParticipantTile));
    expect(
      tiles().where((t) => t.isActiveSpeaker).single.participant.userId,
      'user_1',
    );

    await tester.pumpWidget(_grid(count: 4, activeSpeakerId: 'user_3'));
    await tester.pump();
    expect(
      tiles().where((t) => t.isActiveSpeaker).single.participant.userId,
      'user_3',
      reason: '高亮必须随 activeSpeaker 切换',
    );
    expect(
      tiles().where((t) => t.isActiveSpeaker).length,
      1,
      reason: '任一时刻只有一个高亮 tile',
    );
  });
}
