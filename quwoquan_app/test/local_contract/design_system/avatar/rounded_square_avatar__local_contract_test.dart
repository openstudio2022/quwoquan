import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';

Widget _wrap(Widget child) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      publicMediaDeliveryProvider.overrideWithValue(
        RemotePublicMediaDelivery(_mediaEndpoints),
      ),
    ],
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
    testWidgets(
      'passes raw relative avatar reference with explicit avatar kind',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            RoundedSquareAvatar(
              size: 48,
              imageUrl: '/media/avatar/s/archived-avatar/default/group/v1/default.png',
              name: '契约群',
            ),
          ),
        );

        final image = tester.widget<AppCachedNetworkImage>(
          find.byType(AppCachedNetworkImage),
        );
        // spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-003
        expect(image.cdnPreset, CdnImagePreset.avatar);
        expect(image.mediaKind, MediaDeliveryKind.avatar);
        expect(
          image.imageUrl,
          '/media/avatar/s/archived-avatar/default/group/v1/default.png',
        );
        expect(image.imageUrlCandidates, isNull);
        expect(image.placeholder, isNotNull);
        expect(find.text('契'), findsOneWidget);
      },
    );

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

      // 非空非法引用仍交给获取器判否，消费层不得按URL形态猜测来源。
      expect(
        tester
            .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
            .imageUrl,
        '契',
      );
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.text('契'), findsOneWidget);
    });
  });
}
