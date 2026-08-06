import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';

void main() {
  group('AppMediaImage source normalization', () {
    test('classifies only canonical remote and delivery-key sources', () {
      expect(
        normalizeMediaImageSource('  https://cdn.test/a.png  '),
        'https://cdn.test/a.png',
      );
      expect(isRemoteMediaImageSource('HTTPS://cdn.test/a.png'), isTrue);
      expect(isRemoteMediaImageSource('/tmp/a.png'), isFalse);
      expect(
        isRemoteResolvableMediaImageSource('media/image/object/a.png'),
        isTrue,
      );
      expect(isRemoteResolvableMediaImageSource('avatar/a.png'), isTrue);
      expect(isRemoteResolvableMediaImageSource('file:///tmp/a.png'), isFalse);
    });

    test('normalizes file URI without opening the file system', () {
      expect(
        localMediaImagePath('file:///tmp/a.png'),
        Uri.parse('file:///tmp/a.png').toFilePath(),
      );
      expect(mediaImageProvider('   '), isNull);
    });
  });

  testWidgets('empty source renders the injected placeholder without I/O', (
    tester,
  ) async {
    const placeholderKey = Key('media-placeholder');
    await tester.pumpWidget(
      const MaterialApp(
        home: AppMediaImage(
          imageSource: ' ',
          placeholder: SizedBox(key: placeholderKey),
        ),
      ),
    );

    expect(find.byKey(placeholderKey), findsOneWidget);
  });
}
