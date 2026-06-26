import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

void main() {
  group('RoundedSquareAvatar', () {
    testWidgets('resolves relative media avatar paths before cached avatar load', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const RoundedSquareAvatar(
            size: 48,
            imageUrl:
                '/media/avatar/s/archived-avatar/default/group/v1/default.png',
            name: '契约群',
          ),
        ),
      );

      final image = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      expect(image.cdnPreset, CdnImagePreset.avatar);
      expect(image.imageUrl, startsWith('https://localhost:17100/'));
      expect(
        image.imageUrlCandidates,
        containsAll(<String>[
          'https://localhost:17100/media/avatar/s/archived-avatar/default/group/v1/default.png',
          'https://127.0.0.1:17100/media/avatar/s/archived-avatar/default/group/v1/default.png',
          'https://10.0.2.2:17100/media/avatar/s/archived-avatar/default/group/v1/default.png',
          'https://alpha-avatar.quwoquan-env.test:17100/media/avatar/s/archived-avatar/default/group/v1/default.png',
        ]),
      );
      expect(image.placeholder, isNotNull);
      expect(find.text('契'), findsOneWidget);
    });

    testWidgets(
      'shows explicit fallback icon while network avatar is loading',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            const RoundedSquareAvatar(
              size: 48,
              imageUrl: '/media/avatar/s/archived-avatar/user/u1/v1/avatar.png',
              name: '空头像',
              fallbackIcon: CupertinoIcons.person_fill,
            ),
          ),
        );

        final image = tester.widget<AppCachedNetworkImage>(
          find.byType(AppCachedNetworkImage),
        );
        expect(image.placeholder, isNotNull);
        expect(find.byIcon(CupertinoIcons.person_fill), findsOneWidget);
      },
    );

    testWidgets('falls back to initial for non-url placeholder text', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const RoundedSquareAvatar(size: 48, imageUrl: '契', name: '契约群')),
      );

      expect(find.byType(AppCachedNetworkImage), findsNothing);
      expect(find.text('契'), findsOneWidget);
    });
  });
}
