import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

Widget _wrap(Widget child) {
  return ProviderScope(
    child: CupertinoApp(
      home: CupertinoPageScaffold(child: Center(child: child)),
    ),
  );
}

final _mediaEndpoints = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.example.test/media/avatar',
  imageBaseUrl: 'https://cdn.example.test/media/image',
  videoBaseUrl: 'https://cdn.example.test/media/video',
  attachmentBaseUrl: 'https://cdn.example.test/media/image',
);

void main() {
  group('RoundedSquareAvatar', () {
    testWidgets('resolves relative media avatar paths before cached avatar load', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          RoundedSquareAvatar(
            size: 48,
            imageUrl:
                '/media/avatar/s/archived-avatar/default/group/v1/default.png',
            name: '契约群',
            mediaEndpointConfig: _mediaEndpoints,
          ),
        ),
      );

      final image = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      final candidates = image.imageUrlCandidates ?? const <String>[];
      expect(image.cdnPreset, CdnImagePreset.avatar);
      final expected =
          'https://cdn.example.test/media/avatar/s/archived-avatar/default/group/v1/default.png';
      expect(image.imageUrl, expected);
      expect(candidates, <String>[expected]);
      expect(candidates.join('\n'), isNot(contains('https://10.0.2.2')));
      expect(image.placeholder, isNotNull);
      expect(find.text('契'), findsOneWidget);
    });

    testWidgets(
      'shows explicit fallback icon while network avatar is loading',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            RoundedSquareAvatar(
              size: 48,
              imageUrl: '/media/avatar/s/archived-avatar/user/u1/v1/avatar.png',
              name: '空头像',
              fallbackIcon: CupertinoIcons.person_fill,
              mediaEndpointConfig: _mediaEndpoints,
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
