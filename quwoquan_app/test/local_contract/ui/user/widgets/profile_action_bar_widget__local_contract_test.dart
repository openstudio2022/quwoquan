import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';

RelationshipCapabilityDto _cap(
  String relationState, {
  bool canStartVoiceCall = false,
  bool canStartVideoCall = false,
  bool isBlocked = false,
}) {
  return RelationshipCapabilityDto(
    viewerPersonaId: 'viewer',
    targetPersonaId: 'target',
    relationState: relationState,
    canFollow: false,
    canUnfollow: false,
    canFollowBack: false,
    canGreet: false,
    canOpenConversation: false,
    canCreateDirectConversation: false,
    canSendMessage: false,
    hasPendingGreeting: false,
    hasFormalConversation: false,
    canStartVoiceCall: canStartVoiceCall,
    canStartVideoCall: canStartVideoCall,
    isBlocked: isBlocked,
    isBlockedBy: false,
  );
}

Widget _wrap(Widget child) => MaterialApp(
  home: Scaffold(
    body: Padding(padding: const EdgeInsets.all(16), child: child),
  ),
);

void main() {
  group('ProfileActionBar — 四类主页首屏 CTA 契约', () {
    testWidgets('mine 模式固定渲染分身和资料入口', (tester) async {
      var managed = false;
      var edited = false;

      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.mine,
            isDark: false,
            isFollowing: false,
            onManagePersonas: () => managed = true,
            onEditProfile: () => edited = true,
          ),
        ),
      );
      await tester.pump();

      expect(find.text(ProfileText.personaSwitchProfile), findsOneWidget);
      expect(find.text(ProfileText.profileEditLabel), findsOneWidget);
      expect(find.text(ProfileText.profileBrowseHistory), findsNothing);
      expect(find.text(ContentText.profileShareHomepage), findsNothing);

      await tester.tap(find.text(ProfileText.personaSwitchProfile));
      await tester.tap(find.text(ProfileText.profileEditLabel));
      await tester.pump();

      expect(managed, isTrue);
      expect(edited, isTrue);
    });

    testWidgets('other 未关注时固定渲染关注和私信', (tester) async {
      var followed = false;
      var messaged = false;

      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            isFollowing: false,
            capability: _cap('not_following'),
            onFollow: () => followed = true,
            onMessage: () => messaged = true,
          ),
        ),
      );
      await tester.pump();

      expect(find.text(FoundationText.follow), findsOneWidget);
      expect(find.text(ProfileText.profileDirectMessage), findsOneWidget);
      expect(find.text(ProfileText.profileGreet), findsNothing);
      expect(find.text(CallText.callVoice), findsNothing);
      expect(find.text(CallText.callVideo), findsNothing);

      await tester.tap(find.text(FoundationText.follow));
      await tester.tap(find.text(ProfileText.profileDirectMessage));
      await tester.pump();

      expect(followed, isTrue);
      expect(messaged, isTrue);
    });

    testWidgets('other 已关注时保留关注态和私信', (tester) async {
      var followed = false;

      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: true,
            isFollowing: true,
            capability: _cap('following'),
            onFollow: () => followed = true,
          ),
        ),
      );
      await tester.pump();

      expect(find.text(FoundationText.following), findsOneWidget);
      expect(find.text(ProfileText.profileDirectMessage), findsOneWidget);

      await tester.tap(find.text(FoundationText.following));
      await tester.pump();

      expect(followed, isTrue);
    });

    testWidgets('mutual 且未拉黑时按能力位显示并触发语音/视频入口', (tester) async {
      var voiceCallCount = 0;
      var videoCallCount = 0;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            isFollowing: true,
            capability: _cap(
              'mutual',
              canStartVoiceCall: true,
              canStartVideoCall: true,
            ),
            onVoiceCall: () => voiceCallCount += 1,
            onVideoCall: () => videoCallCount += 1,
          ),
        ),
      );

      expect(find.text(CallText.callVoice), findsOneWidget);
      expect(find.text(CallText.callVideo), findsOneWidget);
      await tester.tap(find.text(CallText.callVoice));
      await tester.tap(find.text(CallText.callVideo));
      expect(voiceCallCount, 1);
      expect(videoCallCount, 1);
    });

    testWidgets('blocked 即使 mutual 且能力位开启也隐藏通话入口', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            isFollowing: true,
            capability: _cap(
              'mutual',
              canStartVoiceCall: true,
              canStartVideoCall: true,
              isBlocked: true,
            ),
          ),
        ),
      );

      expect(find.text(CallText.callVoice), findsNothing);
      expect(find.text(CallText.callVideo), findsNothing);
    });
  });
}
