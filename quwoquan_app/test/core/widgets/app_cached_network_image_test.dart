import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

void main() {
  group('AppCachedNetworkImage', () {
    testWidgets('auto resolves raw background media object keys', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl:
                'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(
        image.imageUrl,
        'http://127.0.0.1:17100/media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
      );
    });

    testWidgets('auto rewrites archived mock seed images before load', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl:
                'media/image/s/mock/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(
        image.imageUrl,
        startsWith(
          'http://127.0.0.1:17100/media/image/s/archived-image/post/fixture_',
        ),
      );
      expect(image.imageUrl, isNot(contains('/mock/seed/')));
    });
  });
}
