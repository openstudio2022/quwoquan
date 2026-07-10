import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/widgets/video_grid_layout.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_tile.dart';

List<CallParticipant> _makeParticipants(int count) {
  return List.generate(
    count,
    (i) => CallParticipant(
      userId: 'user_${i.toString().padLeft(3, '0')}',
      displayName: 'User $i',
      role: i == 0 ? ParticipantRole.initiator : ParticipantRole.invitee,
      status: ParticipantStatus.connected,
      isMuted: i.isEven,
      isCameraOn: i.isOdd,
    ),
  );
}

Widget _buildGrid({required int count, String? activeSpeakerId}) {
  return MaterialApp(
    home: Scaffold(
      body: SizedBox(
        width: 400,
        height: 600,
        child: VideoGridLayout(
          participants: _makeParticipants(count),
          activeSpeakerId: activeSpeakerId,
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('VideoGridLayout — 渲染契约', () {
    testWidgets('1 人 → 1 列网格', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 1));
      await tester.pump();

      expect(find.byType(VideoGridLayout), findsOneWidget);
      expect(find.byType(ParticipantTile), findsOneWidget);
      expect(find.byType(GridView), findsOneWidget);
    });

    testWidgets('2 人 → 1 列网格 2 个 tile', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 2));
      await tester.pump();

      expect(find.byType(ParticipantTile), findsNWidgets(2));
    });

    testWidgets('4 人 → 2 列网格 4 个 tile', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 4));
      await tester.pump();

      expect(find.byType(ParticipantTile), findsNWidgets(4));
    });

    testWidgets('6 人 → 2 列网格 6 个 tile', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 6));
      await tester.pump();

      expect(find.byType(ParticipantTile), findsNWidgets(6));
    });

    testWidgets('9 人 → 3 列网格 9 个 tile', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 9));
      await tester.pump();

      expect(find.byType(ParticipantTile), findsNWidgets(9));
    });

    testWidgets('16 人 → 4 列网格 16 个 tile', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 16));
      await tester.pump();

      expect(find.byType(ParticipantTile), findsNWidgets(16));
    });

    testWidgets('>16 人 → PageView 分页显示', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 20));
      await tester.pump();

      expect(find.byType(VideoGridLayout), findsOneWidget);
      expect(find.byType(PageView), findsOneWidget);
    });

    testWidgets('32 人 → PageView 2 页', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 32));
      await tester.pump();

      expect(find.byType(PageView), findsOneWidget);
      expect(find.byType(ParticipantTile), findsNWidgets(16));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('VideoGridLayout — 交互契约', () {
    testWidgets('activeSpeakerId 标记正确传递给 ParticipantTile', (tester) async {
      await tester.pumpWidget(
        _buildGrid(count: 4, activeSpeakerId: 'user_001'),
      );
      await tester.pump();

      final tiles = tester.widgetList<ParticipantTile>(
        find.byType(ParticipantTile),
      );
      final speakerTiles = tiles.where((t) => t.isActiveSpeaker).toList();
      expect(speakerTiles.length, equals(1));
      expect(speakerTiles.first.participant.userId, equals('user_001'));
    });

    testWidgets('>16 人时 PageView 可滑动翻页', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 24));
      await tester.pump();

      expect(find.byType(PageView), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('VideoGridLayout — 错误态渲染', () {
    testWidgets('空参与者列表 → SizedBox.shrink', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 400,
              height: 600,
              child: VideoGridLayout(
                participants: const [],
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(VideoGridLayout), findsOneWidget);
      expect(find.byType(ParticipantTile), findsNothing);
      expect(find.byType(GridView), findsNothing);
    });

    testWidgets('activeSpeakerId 不匹配任何人 → 无高亮 tile', (tester) async {
      await tester.pumpWidget(
        _buildGrid(count: 4, activeSpeakerId: 'nonexistent_user'),
      );
      await tester.pump();

      final tiles = tester.widgetList<ParticipantTile>(
        find.byType(ParticipantTile),
      );
      final speakerTiles = tiles.where((t) => t.isActiveSpeaker).toList();
      expect(speakerTiles, isEmpty);
    });

    testWidgets('单人参与者无 PageView', (tester) async {
      await tester.pumpWidget(_buildGrid(count: 1));
      await tester.pump();

      expect(find.byType(PageView), findsNothing);
    });
  });
}
