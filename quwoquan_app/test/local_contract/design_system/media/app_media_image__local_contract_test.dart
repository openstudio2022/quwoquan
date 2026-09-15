// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-003
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/media/app_draft_image.dart';

void main() {
  test('发布引用不被归一化，本地草稿必须具名typed构造', () {
    const source = '  media/image/s/p/item/v1/photo.jpg  ';
    const remote = AppMediaImage(imageSource: source);
    const draft = AppMediaImage.draft(source: DraftImageFile('/tmp/a.png'));
    expect(remote.imageSource.codeUnits, source.codeUnits);
    expect(remote.draft, isNull);
    expect(draft.draft!.path, '/tmp/a.png');
    expect(draft.imageSource, isEmpty);
    expect(mediaImageProvider(null), isNull);
    expect(mediaImageProvider(''), isNull);
  });
  testWidgets('真正缺席不发I/O且显示指定占位', (tester) async {
    const placeholderKey = Key('media-placeholder');
    await tester.pumpWidget(
      const MaterialApp(
        home: AppMediaImage(
          imageSource: '',
          placeholder: SizedBox(key: placeholderKey),
        ),
      ),
    );
    expect(find.byKey(placeholderKey), findsOneWidget);
  });
}
