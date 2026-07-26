import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/local_draft_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

class _FakeFileStorageGateway implements FileStorageGateway {
  const _FakeFileStorageGateway();

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async => '/tmp/support';

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<bool> exists(String path) async => false;

  @override
  Future<List<int>> readAsBytes(String path) async => <int>[];

  @override
  Future<String> readAsString(String path) async => '';

  @override
  Future<String> temporaryPath() async => '/tmp';

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> writeAsString(String path, String contents) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];
}

CreateDraft _buildDraft({
  required String id,
  required int updatedAtMs,
  required CreateDraftFlowKind flowKind,
  String title = '',
  String body = '',
  List<String> imagePaths = const <String>[],
  String videoPath = '',
  String videoThumbnail = '',
}) {
  final baseState = CreateEditorState.initial(
    editorKind: flowKind == CreateDraftFlowKind.article
        ? CreateEditorKind.text
        : CreateEditorKind.media,
    draftFlowKind: flowKind,
  );
  final mediaKind = switch (flowKind) {
    CreateDraftFlowKind.article => CreateMediaKind.none,
    CreateDraftFlowKind.image =>
      imagePaths.isEmpty ? CreateMediaKind.none : CreateMediaKind.images,
    CreateDraftFlowKind.video => CreateMediaKind.video,
  };
  final state = baseState.copyWith(
    draftId: id,
    mediaKind: mediaKind,
    imagePaths: imagePaths,
    title: title,
    body: body,
    videoPath: videoPath,
    originalVideoPath: videoPath,
    videoThumbnail: videoThumbnail,
  );
  return CreateDraft(id: id, updatedAtMs: updatedAtMs, state: state);
}

EditorStartAction? _actionFromType(String? raw) {
  return switch ((raw ?? '').trim()) {
    'gallery' => EditorStartAction.gallery,
    'video' => EditorStartAction.video,
    'capture' => EditorStartAction.capture,
    'write' => EditorStartAction.write,
    _ => null,
  };
}

Widget _buildApp() {
  final router = GoRouter(
    initialLocation: AppRoutePaths.localDrafts,
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutePaths.localDrafts,
        builder: (context, state) => const LocalDraftPage(),
      ),
      GoRoute(
        path: AppRoutePaths.createPathTemplate,
        builder: (context, state) {
          return CreatePage(
            initialAction: _actionFromType(state.uri.queryParameters['type']),
            initialDraftId: state.uri.queryParameters['draftId'],
          );
        },
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      ...mockContentFacetOverrides(MockContentRepository()),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      fileStorageGatewayProvider.overrideWithValue(
        const _FakeFileStorageGateway(),
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp.router(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        routerConfig: router,
      ),
    ),
  );
}

void main() {
  group('local_drafts_page', () {
    setUp(() {
      SharedPreferences.setMockInitialValues(<String, Object>{});
    });

    testWidgets('显示设备提示、无图占位并可原地删除草稿', (tester) async {
      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
      );
      await repository.upsertDraft(
        _buildDraft(
          id: 'draft_article',
          updatedAtMs: 1000,
          flowKind: CreateDraftFlowKind.article,
          title: '旧文章',
          body: '文章摘要',
        ),
      );
      await repository.upsertDraft(
        _buildDraft(
          id: 'draft_image',
          updatedAtMs: 2000,
          flowKind: CreateDraftFlowKind.image,
          body: '只有配文，没有图片',
        ),
      );

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      expect(find.byKey(TestKeys.localDraftPage), findsOneWidget);
      expect(
        find.text(UITextConstants.localDraftsDeviceOnlyNotice),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.localDraftMissingImage), findsOneWidget);

      await tester.tap(
        find.byKey(const ValueKey<String>('local_draft_delete_draft_image')),
      );
      await tester.pumpAndSettle();
      expect(
        find.text(UITextConstants.localDraftDeleteConfirmTitle),
        findsOneWidget,
      );
      await tester.tap(find.text(UITextConstants.localDraftDeleteAction));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('local_draft_card_draft_image')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('local_draft_card_draft_article')),
        findsOneWidget,
      );
      expect(find.byKey(TestKeys.localDraftPage), findsOneWidget);
    });

    testWidgets('无图片的图片草稿仍可继续恢复到编辑面', (tester) async {
      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
      );
      await repository.upsertDraft(
        _buildDraft(
          id: 'draft_image_resume',
          updatedAtMs: 3000,
          flowKind: CreateDraftFlowKind.image,
          body: '继续补图的图片草稿',
        ),
      );

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          const ValueKey<String>('local_draft_card_draft_image_resume'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(TestKeys.createPage), findsOneWidget);
      expect(find.text('继续补图的图片草稿'), findsOneWidget);
    });

    testWidgets('视频主文件缺失时提示不可恢复并允许删除', (tester) async {
      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
      );
      await repository.upsertDraft(
        _buildDraft(
          id: 'draft_video_missing',
          updatedAtMs: 4000,
          flowKind: CreateDraftFlowKind.video,
          title: '缺视频文件',
          body: '只剩文案',
        ),
      );

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          const ValueKey<String>('local_draft_card_draft_video_missing'),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.localDraftUnavailableTitle),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.localDraftMissingVideoDesc),
        findsOneWidget,
      );

      await tester.tap(find.text(UITextConstants.localDraftDeleteAction));
      await tester.pumpAndSettle();

      expect(find.byKey(TestKeys.localDraftEmptyState), findsOneWidget);
    });
  });
}
