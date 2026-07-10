import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_slogan_card.dart';

void main() {
  testWidgets('ProfileSloganCard 点击整块 slogan 触发编辑入口', (tester) async {
    var tapped = false;

    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: ProfileSloganCard(
            isDark: false,
            bio: '用户与影像，记录思考与生活',
            onTap: () => tapped = true,
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey<String>('profile-slogan-card')));
    expect(tapped, isTrue);
  });

  testWidgets('ProfileSloganCard 超过两行显示全部入口并可展开', (tester) async {
    const longBio = '用户与影像，记录思考与生活，也记录旅行中的观察、产品里的灵感、城市里偶然遇见的人和故事。';

    await tester.pumpWidget(
      const CupertinoApp(
        home: CupertinoPageScaffold(
          child: Center(
            child: SizedBox(
              width: 220,
              child: ProfileSloganCard(isDark: false, bio: longBio),
            ),
          ),
        ),
      ),
    );

    expect(find.text('...全部'), findsOneWidget);

    await tester.tap(find.text('...全部'));
    await tester.pump();

    expect(find.text('...全部'), findsNothing);
    expect(find.text(longBio), findsOneWidget);
  });
}
