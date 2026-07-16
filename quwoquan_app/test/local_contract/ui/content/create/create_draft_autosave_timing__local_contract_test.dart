import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';

class _CreateHostApp extends StatelessWidget {
  const _CreateHostApp();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.of(context).push<void>(
              MaterialPageRoute<void>(builder: (_) => const CreatePage()),
            );
          },
          child: const Text('打开创作'),
        ),
      ),
    );
  }
}

Widget _buildApp() {
  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      ...mockContentFacetOverrides(MockContentRepository()),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const _CreateHostApp(),
      ),
    ),
  );
}

Widget _buildCreatePageApp({String? initialTabKey}) {
  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      ...mockContentFacetOverrides(MockContentRepository()),
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

CreateDraft _buildDraft({
  required String id,
  required int updatedAtMs,
  String body = '',
}) {
  final state = CreateEditorState.initial().copyWith(draftId: id, body: body);
  return CreateDraft(id: id, updatedAtMs: updatedAtMs, state: state);
}

Future<void> _seedExistingDraft(
  SharedPreferencesCreateDraftRepository repository,
) async {
  await repository.upsertDraft(
    _buildDraft(id: 'existing_draft', updatedAtMs: 1000, body: '已有草稿不能被误删'),
    currentDraftId: 'existing_draft',
  );
}

Future<void> _expectDiscardDoesNotDeleteExistingDraft(
  WidgetTester tester, {
  String? initialTabKey,
  required Key inputKey,
  Future<void> Function(WidgetTester tester)? prepareEditor,
}) async {
  final repository = SharedPreferencesCreateDraftRepository(
    scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
  );
  await _seedExistingDraft(repository);

  await tester.pumpWidget(_buildCreatePageApp(initialTabKey: initialTabKey));
  await tester.pumpAndSettle();

  if (prepareEditor != null) {
    await prepareEditor(tester);
  }

  await tester.enterText(find.byKey(inputKey), '新的临时内容');
  await tester.pump();

  await tester.tap(find.byKey(TestKeys.createCloseButton));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(TestKeys.createDiscardAndExitButton));
  await tester.pumpAndSettle();

  final snapshot = await repository.load();
  expect(snapshot.drafts, hasLength(1));
  expect(snapshot.drafts.single.id, 'existing_draft');
}

void main() {
  group('create_draft_autosave_timing', () {
    setUp(() {
      SharedPreferences.setMockInitialValues(<String, Object>{});
    });

    testWidgets('dirty_state_saves_every_10s_and_flushes_on_blur', (
      tester,
    ) async {
      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
      );

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('打开创作'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(TestKeys.createMomentInput), '第一段草稿');
      await tester.pump();

      await tester.pump(const Duration(seconds: 5));
      final beforeFlush = await repository.load();
      expect(beforeFlush.drafts, isEmpty);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final lifecycleSaved = await repository.load();
      expect(lifecycleSaved.drafts, hasLength(1));
      expect(lifecycleSaved.drafts.single.state.body, contains('第一段草稿'));
      final firstSavedAt = lifecycleSaved.drafts.single.updatedAtMs;

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();

      await tester.enterText(find.byType(EditableText).last, '第一段草稿，补充到第二版');
      await tester.pump();
      await tester.pump(const Duration(seconds: 10));
      await tester.pump();

      final timerSaved = await repository.load();
      expect(timerSaved.drafts, hasLength(1));
      expect(timerSaved.drafts.single.state.body, contains('补充到第二版'));
      expect(timerSaved.drafts.single.updatedAtMs, greaterThan(firstSavedAt));

      final secondSavedAt = timerSaved.drafts.single.updatedAtMs;
      await tester.pump(const Duration(seconds: 11));
      await tester.pump();
      final noExtraWrite = await repository.load();
      expect(noExtraWrite.drafts.single.updatedAtMs, secondSavedAt);

      await tester.tap(find.byKey(TestKeys.createCloseButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(TestKeys.createDiscardAndExitButton));
      await tester.pumpAndSettle();

      await tester.pump(const Duration(seconds: 11));
      await tester.pump();

      final afterDiscard = await repository.load();
      expect(afterDiscard.drafts, isEmpty);
      expect(afterDiscard.currentDraftId, isNull);
    });

    testWidgets(
      'discard article editor only affects current unsaved editor scope',
      (tester) async {
        await _expectDiscardDoesNotDeleteExistingDraft(
          tester,
          inputKey: TestKeys.createMomentInput,
        );
      },
    );

    testWidgets(
      'discard photo editor only affects current unsaved editor scope',
      (tester) async {
        await _expectDiscardDoesNotDeleteExistingDraft(
          tester,
          initialTabKey: 'photo',
          inputKey: TestKeys.createPhotoBodyInput,
          prepareEditor: (tester) async {
            final container = ProviderScope.containerOf(
              tester.element(find.byType(CreatePage)),
            );
            final notifier = container.read(createEditorProvider.notifier);
            notifier.setImages(<String>[
              '/tmp/a.jpg',
            ], editorKind: CreateEditorKind.media);
            await tester.pumpAndSettle();
          },
        );
      },
    );

    testWidgets(
      'discard video editor only affects current unsaved editor scope',
      (tester) async {
        await _expectDiscardDoesNotDeleteExistingDraft(
          tester,
          initialTabKey: 'video',
          inputKey: TestKeys.createVideoBodyInput,
          prepareEditor: (tester) async {
            final container = ProviderScope.containerOf(
              tester.element(find.byType(CreatePage)),
            );
            final notifier = container.read(createEditorProvider.notifier);
            notifier.setVideo(
              '/tmp/demo.mp4',
              editorKind: CreateEditorKind.media,
              thumbnail: '/tmp/demo_cover.jpg',
            );
            await tester.pumpAndSettle();
          },
        );
      },
    );
  });
}
