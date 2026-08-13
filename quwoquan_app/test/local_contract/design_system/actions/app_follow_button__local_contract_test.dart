// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#open-001

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

Widget _host(Widget child, {Brightness brightness = Brightness.light}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: Center(child: child),
  );
}

void main() {
  group('AppFollowButton — 共享关注 pill 合约', () {
    testWidgets('未关注/已关注两态文案与点击回调', (tester) async {
      var tapped = 0;
      await tester.pumpWidget(
        _host(
          AppFollowButton(isFollowing: false, onPressed: () => tapped += 1),
        ),
      );
      expect(find.text(FoundationText.follow), findsOneWidget);
      await tester.tap(find.byType(AppFollowButton));
      expect(tapped, 1);

      await tester.pumpWidget(
        _host(AppFollowButton(isFollowing: true, onPressed: () {})),
      );
      expect(find.text(FoundationText.following), findsOneWidget);
    });

    testWidgets('label 可覆盖默认文案（回关等关系语义）', (tester) async {
      await tester.pumpWidget(
        _host(
          AppFollowButton(
            isFollowing: false,
            label: FoundationText.followBack,
            onPressed: () {},
          ),
        ),
      );
      expect(find.text(FoundationText.followBack), findsOneWidget);
      expect(find.text(FoundationText.follow), findsNothing);
    });

    testWidgets('onMedia 变体使用白字实底（沉浸式深色媒体面）', (tester) async {
      await tester.pumpWidget(
        _host(
          AppFollowButton(
            isFollowing: false,
            style: AppFollowButtonStyle.onMedia,
            onPressed: () {},
          ),
        ),
      );
      final text = tester.widget<Text>(find.text(FoundationText.follow));
      expect(text.style?.color, AppColors.white);
      final container = tester.widget<Container>(
        find.descendant(
          of: find.byType(AppFollowButton),
          matching: find.byType(Container),
        ),
      );
      expect(
        (container.decoration as BoxDecoration?)?.color,
        AppColors.primaryColor,
      );
    });

    testWidgets('pillKey 透传为测试探针', (tester) async {
      const probe = ValueKey<String>('home-post-author-follow-button');
      await tester.pumpWidget(
        _host(
          AppFollowButton(
            isFollowing: false,
            pillKey: probe,
            onPressed: () {},
          ),
        ),
      );
      expect(find.byKey(probe), findsOneWidget);
    });
  });
}
