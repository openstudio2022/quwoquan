import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';

/// T2 Widget 测试：ProfileActionBar 五态按钮矩阵
///
/// 守护：
/// - 五种关系状态下按钮布局的正确渲染
/// - 回调在正确条件下触发
/// - 空 capability 时回退到 legacy 逻辑不崩溃

RelationshipCapabilityDto _cap(String tier, {
  bool canGreet = false,
  bool canOpenConversation = false,
  bool canAddSameInterest = false,
  bool canSetCloseFriend = false,
  bool canStartVoiceCall = false,
  bool canStartVideoCall = false,
}) => RelationshipCapabilityDto(
  viewerSubAccountId: 'viewer',
  targetSubAccountId: 'target',
  relationTier: tier,
  canGreet: canGreet,
  canOpenConversation: canOpenConversation,
  canAddSameInterest: canAddSameInterest,
  canSetCloseFriend: canSetCloseFriend,
  canStartVoiceCall: canStartVoiceCall,
  canStartVideoCall: canStartVideoCall,
  isBlocked: false,
  isBlockedBy: false,
);

Widget _wrap(Widget child) => MaterialApp(
  home: Scaffold(
    body: Padding(
      padding: const EdgeInsets.all(16),
      child: child,
    ),
  ),
);

Finder _actionBarText(String label) {
  return find.descendant(
    of: find.byType(ProfileActionBar),
    matching: find.text(label),
  );
}

void main() {
  // ── 渲染契约 ─────────────────────────────────────────────────────────────────

  group('ProfileActionBar — 渲染契约', () {
    testWidgets('mine 模式渲染编辑资料和分身管理按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(mode: ProfileMode.mine, isDark: false),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profilePersonasLabel), findsOneWidget);
    });

    testWidgets('same_interest 渲染私信、视频通话、语音通话三等分按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap(
            'same_interest',
            canOpenConversation: true,
            canStartVoiceCall: true,
            canStartVideoCall: true,
          ),
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.callVideo), findsOneWidget);
      expect(find.text(UITextConstants.callVoice), findsOneWidget);
    });

    testWidgets('close_friend 也渲染三等分按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap(
            'close_friend',
            canOpenConversation: true,
            canStartVoiceCall: true,
            canStartVideoCall: true,
          ),
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.callVideo), findsOneWidget);
      expect(find.text(UITextConstants.callVoice), findsOneWidget);
    });

    testWidgets('following_only 渲染打招呼和已关注', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap('following_only', canGreet: true),
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.profileGreet), findsOneWidget);
      expect(find.text(UITextConstants.following), findsOneWidget);
    });

    testWidgets('none 陌生人渲染全宽关注按钮', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap('none'),
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.follow), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsNothing);
    });

    testWidgets('capability 为 null 时回退渲染 legacy 关注/私信', (tester) async {
      await tester.pumpWidget(_wrap(
        const ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
        ),
      ));
      await tester.pump();

      expect(find.text(UITextConstants.follow), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });
  });

  // ── 交互契约 ─────────────────────────────────────────────────────────────────

  group('ProfileActionBar — 交互契约', () {
    testWidgets('mine 模式 onEditProfile 回调被触发', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.mine,
          isDark: false,
          onEditProfile: () => tapped = true,
        ),
      ));
      await tester.pump();
      await tester.tap(find.text(UITextConstants.profileEditLabel));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('following_only 且 canGreet=true 时 onGreet 被触发', (tester) async {
      var greeted = false;
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap('following_only', canGreet: true),
          onGreet: () => greeted = true,
        ),
      ));
      await tester.pump();
      await tester.tap(find.text(UITextConstants.profileGreet));
      await tester.pump();

      expect(greeted, true);
    });

    testWidgets('same_interest 且 canStartVoiceCall=true 时 onVoiceCall 被触发', (tester) async {
      var voiceCalled = false;
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap(
            'same_interest',
            canOpenConversation: true,
            canStartVoiceCall: true,
            canStartVideoCall: true,
          ),
          onVoiceCall: () => voiceCalled = true,
        ),
      ));
      await tester.pump();
      await tester.tap(find.text(UITextConstants.callVoice));
      await tester.pump();

      expect(voiceCalled, true);
    });

    testWidgets('same_interest 且 canStartVideoCall=true 时 onVideoCall 被触发', (tester) async {
      var videoCalled = false;
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap(
            'same_interest',
            canOpenConversation: true,
            canStartVoiceCall: true,
            canStartVideoCall: true,
          ),
          onVideoCall: () => videoCalled = true,
        ),
      ));
      await tester.pump();
      await tester.tap(find.text(UITextConstants.callVideo));
      await tester.pump();

      expect(videoCalled, true);
    });

    testWidgets('none 状态 onFollow 被触发', (tester) async {
      var followed = false;
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap('none'),
          onFollow: () => followed = true,
        ),
      ));
      await tester.pump();
      await tester.tap(find.text(UITextConstants.follow));
      await tester.pump();

      expect(followed, true);
    });
  });

  // ── 错误态渲染 ────────────────────────────────────────────────────────────────

  group('ProfileActionBar — 错误态渲染', () {
    testWidgets('capability 为 null 且所有回调为 null 不崩溃', (tester) async {
      await tester.pumpWidget(_wrap(
        const ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
        ),
      ));
      await tester.pump();
      expect(_actionBarText(UITextConstants.follow), findsAtLeastNWidgets(1));
      expect(
        _actionBarText(UITextConstants.profileDirectMessage),
        findsOneWidget,
      );
    });

    testWidgets('未知 relationTier 不崩溃（fallback 到 legacy）', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: false,
          capability: _cap('future_unknown_tier'),
        ),
      ));
      await tester.pump();
      expect(find.byType(ProfileActionBar), findsOneWidget);
    });

    testWidgets('暗色模式渲染不崩溃', (tester) async {
      await tester.pumpWidget(_wrap(
        ProfileActionBar(
          mode: ProfileMode.other,
          isDark: true,
          capability: _cap(
            'same_interest',
            canOpenConversation: true,
            canStartVoiceCall: true,
            canStartVideoCall: true,
          ),
        ),
      ));
      await tester.pump();
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });
  });
}
