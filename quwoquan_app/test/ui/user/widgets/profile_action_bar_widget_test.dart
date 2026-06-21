import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';

RelationshipCapabilityDto _cap(String relationState) {
  return RelationshipCapabilityDto(
    viewerSubAccountId: 'viewer',
    targetSubAccountId: 'target',
    relationState: relationState,
    isBlocked: false,
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

      expect(find.text(UITextConstants.personaSwitchProfile), findsOneWidget);
      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profileBrowseHistory), findsNothing);
      expect(find.text(UITextConstants.profileShareHomepage), findsNothing);

      await tester.tap(find.text(UITextConstants.personaSwitchProfile));
      await tester.tap(find.text(UITextConstants.profileEditLabel));
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

      expect(find.text(UITextConstants.follow), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);
      expect(find.text(UITextConstants.profileGreet), findsNothing);
      expect(find.text(UITextConstants.callVoice), findsNothing);
      expect(find.text(UITextConstants.callVideo), findsNothing);

      await tester.tap(find.text(UITextConstants.follow));
      await tester.tap(find.text(UITextConstants.profileDirectMessage));
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

      expect(find.text(UITextConstants.following), findsOneWidget);
      expect(find.text(UITextConstants.profileDirectMessage), findsOneWidget);

      await tester.tap(find.text(UITextConstants.following));
      await tester.pump();

      expect(followed, isTrue);
    });
  });
}
