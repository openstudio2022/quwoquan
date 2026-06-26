import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildCreatePageApp({String? initialTabKey}) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(MockContentRepository()),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CreatePage(initialTabKey: initialTabKey),
      ),
    ),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('图片创作页使用统一标题 token，首屏标题不再淡化', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final title = tester.widget<Text>(find.text('图片创作'));
    expect(
      title.style?.color,
      AppNavigationSemanticConstants.barTitleColor(false),
    );

    final opacity = tester.widget<Opacity>(
      find
          .ancestor(of: find.text('图片创作'), matching: find.byType(Opacity))
          .first,
    );
    expect(opacity.opacity, 1);
  });

  testWidgets('图片网格拖拽悬停时目标区间即时移位，松手后 provider 顺序提交', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      '/tmp/a.jpg',
      '/tmp/b.jpg',
      '/tmp/c.jpg',
      '/tmp/d.jpg',
    ], editorKind: CreateEditorKind.media);
    await tester.pumpAndSettle();

    expect(find.byType(MediaReorderableView), findsOneWidget);

    final aRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/a.jpg')),
    );
    final bRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/b.jpg')),
    );
    final start = tester.getCenter(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/a.jpg')),
    );
    final target = tester.getCenter(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/c.jpg')),
    );

    final gesture = await tester.startGesture(start);
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 80));
    await gesture.moveBy(target - start);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final bRect = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/b.jpg')),
    );
    final cRect = tester.getRect(
      find.byKey(const ValueKey<String>('create-media-tile-/tmp/c.jpg')),
    );
    expect(bRect.topLeft.dx, closeTo(aRectBefore.left, 1));
    expect(bRect.topLeft.dy, closeTo(aRectBefore.top, 1));
    expect(cRect.topLeft.dx, closeTo(bRectBefore.left, 1));
    expect(cRect.topLeft.dy, closeTo(bRectBefore.top, 1));

    await gesture.up();
    await tester.pumpAndSettle();

    final state = container.read(createEditorProvider);
    expect(state.imagePaths, <String>[
      '/tmp/b.jpg',
      '/tmp/c.jpg',
      '/tmp/a.jpg',
      '/tmp/d.jpg',
    ]);
  });
}
