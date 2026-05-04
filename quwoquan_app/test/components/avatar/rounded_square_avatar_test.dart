import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';

Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

void main() {
  group('RoundedSquareAvatar', () {
    testWidgets('resolves relative media avatar paths before Image.network', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const RoundedSquareAvatar(
            size: 48,
            imageUrl: '/media/avatar/default/group/v1/default.png',
            name: '契约群',
          ),
        ),
      );

      final image = tester.widget<Image>(find.byType(Image));
      final provider = image.image as NetworkImage;
      expect(
        provider.url,
        'http://127.0.0.1:18088/media/avatar/default/group/v1/default.png',
      );
      expect(find.text('契'), findsNothing);
    });

    testWidgets('falls back to initial for non-url placeholder text', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const RoundedSquareAvatar(size: 48, imageUrl: '契', name: '契约群')),
      );

      expect(find.byType(Image), findsNothing);
      expect(find.text('契'), findsOneWidget);
    });
  });
}
