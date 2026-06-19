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
}
