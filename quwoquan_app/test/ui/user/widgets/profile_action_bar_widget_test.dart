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
/// - 空 capability 时他人主页不渲染操作条（不崩溃）

RelationshipCapabilityDto _cap(
  String tier, {
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
    body: Padding(padding: const EdgeInsets.all(16), child: child),
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
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.mine,
            isDark: false,
            onManagePersonas: () {},
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profilePersonasLabel), findsOneWidget);
    });

    testWidgets('mine 模式未提供分身回调时隐藏分身管理按钮', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const ProfileActionBar(
            mode: ProfileMode.mine,
            isDark: false,
            onManagePersonas: null,
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profilePersonasLabel), findsNothing);
    });

    testWidgets('mutual 渲染私信、视频通话、语音通话三等分按钮', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap(
              'mutual',
              canOpenConversation: true,
              canStartVoiceCall: true,
              canStartVideoCall: true,
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.callVideo), findsOneWidget);
      expect(find.text(UITextConstants.callVoice), findsOneWidget);
    });

    testWidgets('followed_by 渲染回关和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('followed_by', canOpenConversation: true),
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.followBack), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.callVideo), findsNothing);
      expect(find.text(UITextConstants.callVoice), findsNothing);
    });

    testWidgets('following 渲染已关注和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('following', canOpenConversation: true),
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.following), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });

    testWidgets('not_following 渲染关注和私信', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('not_following', canOpenConversation: true),
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.follow), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });

    testWidgets('capability 为 null 时他人主页不渲染操作按钮', (tester) async {
      await tester.pumpWidget(
        _wrap(const ProfileActionBar(mode: ProfileMode.other, isDark: false)),
      );
      await tester.pump();

      expect(find.text(UITextConstants.follow), findsNothing);
      expect(find.text(UITextConstants.profileDirectMessage), findsNothing);
    });
  });

  // ── 交互契约 ─────────────────────────────────────────────────────────────────

  group('ProfileActionBar — 交互契约', () {
    testWidgets('mine 模式 onEditProfile 回调被触发', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.mine,
            isDark: false,
            onEditProfile: () => tapped = true,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(UITextConstants.profileEditLabel));
      await tester.pump();

      expect(tapped, true);
    });

    testWidgets('following 状态点击已关注按钮时 onFollow 被触发', (tester) async {
      var followed = false;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('following', canOpenConversation: true),
            onFollow: () => followed = true,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(UITextConstants.following));
      await tester.pump();

      expect(followed, true);
    });

    testWidgets('mutual 且 canStartVoiceCall=true 时 onVoiceCall 被触发', (
      tester,
    ) async {
      var voiceCalled = false;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap(
              'mutual',
              canOpenConversation: true,
              canStartVoiceCall: true,
              canStartVideoCall: true,
            ),
            onVoiceCall: () => voiceCalled = true,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(UITextConstants.callVoice));
      await tester.pump();

      expect(voiceCalled, true);
    });

    testWidgets('mutual 且 canStartVideoCall=true 时 onVideoCall 被触发', (
      tester,
    ) async {
      var videoCalled = false;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap(
              'mutual',
              canOpenConversation: true,
              canStartVoiceCall: true,
              canStartVideoCall: true,
            ),
            onVideoCall: () => videoCalled = true,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(UITextConstants.callVideo));
      await tester.pump();

      expect(videoCalled, true);
    });

    testWidgets('not_following 状态 onFollow 被触发', (tester) async {
      var followed = false;
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('not_following', canOpenConversation: true),
            onFollow: () => followed = true,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(UITextConstants.follow));
      await tester.pump();

      expect(followed, true);
    });
  });

  // ── 错误态渲染 ────────────────────────────────────────────────────────────────

  group('ProfileActionBar — 错误态渲染', () {
    testWidgets('capability 为 null 且所有回调为 null 不崩溃', (tester) async {
      await tester.pumpWidget(
        _wrap(const ProfileActionBar(mode: ProfileMode.other, isDark: false)),
      );
      await tester.pump();
      expect(_actionBarText(UITextConstants.follow), findsNothing);
      expect(
        _actionBarText(UITextConstants.profileDirectMessage),
        findsNothing,
      );
    });

    testWidgets('未知 relationTier 不崩溃（按 not_following 展示）', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: false,
            capability: _cap('future_unknown_tier'),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(ProfileActionBar), findsOneWidget);
    });

    testWidgets('暗色模式渲染不崩溃', (tester) async {
      await tester.pumpWidget(
        _wrap(
          ProfileActionBar(
            mode: ProfileMode.other,
            isDark: true,
            capability: _cap(
              'mutual',
              canOpenConversation: true,
              canStartVoiceCall: true,
              canStartVideoCall: true,
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
    });
  });
}
