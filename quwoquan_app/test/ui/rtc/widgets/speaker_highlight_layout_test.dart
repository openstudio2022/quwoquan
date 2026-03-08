import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/widgets/speaker_highlight_layout.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_tile.dart';

List<CallParticipant> _makeParticipants(int count) {
  return List.generate(
    count,
    (i) => CallParticipant(
      userId: 'user_${i.toString().padLeft(3, '0')}',
      displayName: 'User $i',
      role: i == 0 ? ParticipantRole.initiator : ParticipantRole.invitee,
      status: ParticipantStatus.connected,
      isCameraOn: i < 2,
    ),
  );
}

Widget _buildLayout({
  int participantCount = 4,
  CallParticipant? activeSpeaker,
  String? lockedSpeakerId,
  ValueChanged<String>? onTapThumbnail,
}) {
  final participants = _makeParticipants(participantCount);
  return MaterialApp(
    home: Scaffold(
      body: SizedBox(
        width: 400,
        height: 700,
        child: SpeakerHighlightLayout(
          participants: participants,
          activeSpeaker: activeSpeaker ?? participants.first,
          lockedSpeakerId: lockedSpeakerId,
          onTapThumbnail: onTapThumbnail,
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('SpeakerHighlightLayout — 渲染契约', () {
    testWidgets('大画面占 flex 7（70% 高度）', (tester) async {
      await tester.pumpWidget(_buildLayout());
      await tester.pump();

      expect(find.byType(SpeakerHighlightLayout), findsOneWidget);

      final expandedFinder = find.byWidgetPredicate(
        (w) => w is Expanded && w.flex == 7,
      );
      expect(expandedFinder, findsOneWidget);
    });

    testWidgets('缩略行使用 ListView 横向滚动', (tester) async {
      await tester.pumpWidget(_buildLayout(participantCount: 5));
      await tester.pump();

      final listView = find.byWidgetPredicate(
        (w) => w is ListView && w.scrollDirection == Axis.horizontal,
      );
      expect(listView, findsOneWidget);
    });

    testWidgets('activeSpeaker 作为大画面', (tester) async {
      final participants = _makeParticipants(4);
      final speaker = participants[1];

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 400,
              height: 700,
              child: SpeakerHighlightLayout(
                participants: participants,
                activeSpeaker: speaker,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      final tiles = tester.widgetList<ParticipantTile>(
        find.byType(ParticipantTile),
      );
      final activeTiles = tiles.where((t) => t.isActiveSpeaker).toList();
      expect(activeTiles.isNotEmpty, isTrue);
      expect(activeTiles.first.participant.userId, equals('user_001'));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('SpeakerHighlightLayout — 交互契约', () {
    testWidgets('点击缩略图触发 onTapThumbnail 回调', (tester) async {
      String? tappedUserId;
      await tester.pumpWidget(
        _buildLayout(
          participantCount: 4,
          onTapThumbnail: (userId) => tappedUserId = userId,
        ),
      );
      await tester.pump();

      final thumbnailTiles = tester.widgetList<ParticipantTile>(
        find.byType(ParticipantTile),
      );
      expect(thumbnailTiles.length, greaterThan(1));

      final thumbnails = find.byType(GestureDetector);
      if (thumbnails.evaluate().length > 1) {
        await tester.tap(thumbnails.at(1));
        await tester.pump();
        expect(tappedUserId, isNotNull);
      }

      expect(find.byType(SpeakerHighlightLayout), findsOneWidget);
    });

    testWidgets('locked speaker 显示固定图标', (tester) async {
      await tester.pumpWidget(
        _buildLayout(
          participantCount: 4,
          lockedSpeakerId: 'user_001',
        ),
      );
      await tester.pump();

      expect(find.byIcon(Icons.push_pin), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('SpeakerHighlightLayout — 错误态渲染', () {
    testWidgets('空参与者列表 → SizedBox.shrink', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 400,
              height: 700,
              child: SpeakerHighlightLayout(
                participants: const [],
                activeSpeaker: null,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(SpeakerHighlightLayout), findsOneWidget);
      expect(find.byType(ParticipantTile), findsNothing);
    });

    testWidgets('仅 1 人时无缩略行', (tester) async {
      final participants = _makeParticipants(1);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 400,
              height: 700,
              child: SpeakerHighlightLayout(
                participants: participants,
                activeSpeaker: participants.first,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(ParticipantTile), findsOneWidget);
      final listView = find.byWidgetPredicate(
        (w) => w is ListView && w.scrollDirection == Axis.horizontal,
      );
      expect(listView, findsNothing);
    });

    testWidgets('lockedSpeakerId 不匹配任何人不崩溃', (tester) async {
      await tester.pumpWidget(
        _buildLayout(
          participantCount: 4,
          lockedSpeakerId: 'nonexistent_user',
        ),
      );
      await tester.pump();

      expect(find.byType(SpeakerHighlightLayout), findsOneWidget);
      expect(find.byIcon(Icons.push_pin), findsNothing);
    });
  });
}
