// spec_ref: specs/feature-tree/discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md#gwt-002.t6

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_draft_local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
  final articleDocument = flowKind == CreateDraftFlowKind.article
      ? ArticleDocumentData(
          nodes: <ArticleDocumentNode>[
            if (title.trim().isNotEmpty)
              ArticleDocumentNode(
                id: 'title',
                type: ArticleDocumentNodeType.documentTitle,
                text: title,
              ),
            ArticleDocumentNode(
              id: 'paragraph_0',
              type: ArticleDocumentNodeType.paragraph,
              text: body,
            ),
          ],
        )
      : baseState.articleDocument;
  final state = baseState.copyWith(
    draftId: id,
    mediaKind: mediaKind,
    imagePaths: imagePaths,
    title: title,
    body: body,
    articleDocument: articleDocument,
    videoPath: videoPath,
    originalVideoPath: videoPath,
    videoThumbnail: videoThumbnail,
  );
  return CreateDraft(id: id, updatedAtMs: updatedAtMs, state: state);
}

void main() {
  group('create_local_draft_repository', () {
    setUp(() {
      SharedPreferences.setMockInitialValues(<String, Object>{});
    });

    test('canonical scoped storage preserves flow kind and order', () async {
      final scopeKey = CreateDraftLocalStorage.scopeKeyForUser('user_001');
      final articleDraft = _buildDraft(
        id: 'draft_article',
        updatedAtMs: 1000,
        flowKind: CreateDraftFlowKind.article,
        title: '旧文章',
        body: '文章内容',
      );
      final imageDraft = _buildDraft(
        id: 'draft_image',
        updatedAtMs: 3000,
        flowKind: CreateDraftFlowKind.image,
        body: '只剩配文',
      );

      SharedPreferences.setMockInitialValues(<String, Object>{
        CreateDraftLocalStorage.scopedIndexKey(scopeKey): jsonEncode(<String>[
          'draft_article',
          'draft_image',
        ]),
        CreateDraftLocalStorage.scopedDraftPayloadKey(
          scopeKey,
          articleDraft.id,
        ): jsonEncode(
          articleDraft.toStorageMap(),
        ),
        CreateDraftLocalStorage.scopedDraftPayloadKey(scopeKey, imageDraft.id):
            jsonEncode(imageDraft.toStorageMap()),
        CreateDraftLocalStorage.scopedCurrentDraftIdKey(scopeKey):
            'draft_image',
      });

      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: scopeKey,
      );
      final snapshot = await repository.load();
      final prefs = await SharedPreferences.getInstance();

      expect(
        snapshot.drafts.map((draft) => draft.id).toList(growable: false),
        <String>['draft_image', 'draft_article'],
      );
      expect(snapshot.currentDraftId, 'draft_image');
      expect(
        snapshot.draftById('draft_image')?.flowKind,
        CreateDraftFlowKind.image,
      );
      expect(snapshot.draftById('draft_image')?.state.imagePaths, isEmpty);
      expect(
        prefs.getString(
          CreateDraftLocalStorage.scopedCurrentDraftIdKey(scopeKey),
        ),
        'draft_image',
      );
      expect(
        prefs.getString(CreateDraftLocalStorage.scopedIndexKey(scopeKey)),
        isNotNull,
      );
      expect(
        prefs.getString(
          CreateDraftLocalStorage.scopedDraftPayloadKey(
            scopeKey,
            'draft_image',
          ),
        ),
        isNotNull,
      );
    });

    test('draft namespaces stay isolated per user scope', () async {
      final userA = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_a'),
      );
      final userB = SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_b'),
      );

      await userA.upsertDraft(
        _buildDraft(
          id: 'draft_video',
          updatedAtMs: 2000,
          flowKind: CreateDraftFlowKind.video,
          body: '只属于 A 的草稿',
          videoPath: '/tmp/video.mp4',
        ),
      );

      final snapshotA = await userA.load();
      final snapshotB = await userB.load();

      expect(snapshotA.drafts, hasLength(1));
      expect(snapshotA.drafts.single.id, 'draft_video');
      expect(snapshotB.drafts, isEmpty);
      expect(await userB.loadDraft('draft_video'), isNull);
    });

    test('匿名 actor 草稿安全并入账号 scope，冲突保留较新版本并清除源副本', () async {
      final sourceScope = CreateDraftLocalStorage.scopeKeyForUser(
        'anonymous_persona',
      );
      final targetScope = CreateDraftLocalStorage.scopeKeyForUser(
        'authenticated_persona',
      );
      final sourceCurrent = _buildDraft(
        id: 'draft_source_current',
        updatedAtMs: 3000,
        flowKind: CreateDraftFlowKind.article,
        body: '游客当前草稿',
      );
      final sourceConflict = _buildDraft(
        id: 'draft_shared',
        updatedAtMs: 2000,
        flowKind: CreateDraftFlowKind.image,
        body: '游客较旧版本',
      );
      final targetConflict = _buildDraft(
        id: 'draft_shared',
        updatedAtMs: 5000,
        flowKind: CreateDraftFlowKind.image,
        body: '账号较新版本',
      );
      final targetOnly = _buildDraft(
        id: 'draft_target_only',
        updatedAtMs: 1000,
        flowKind: CreateDraftFlowKind.video,
        body: '账号原有草稿',
        videoPath: '/tmp/account.mp4',
      );
      await CreateDraftLocalStorage.persistScopedDrafts(
        sourceScope,
        <CreateDraft>[sourceCurrent, sourceConflict],
        currentId: sourceCurrent.id,
      );
      await CreateDraftLocalStorage.persistScopedDrafts(
        targetScope,
        <CreateDraft>[targetConflict, targetOnly],
        currentId: targetOnly.id,
      );

      final adopted = await CreateDraftLocalStorage.adoptScopedDrafts(
        sourceScopeKey: sourceScope,
        targetScopeKey: targetScope,
      );
      final sourceAfter =
          await CreateDraftLocalStorage.loadScopedDraftsWithCurrentId(
            sourceScope,
          );
      final prefs = await SharedPreferences.getInstance();

      expect(adopted.drafts, hasLength(3));
      expect(adopted.currentId, sourceCurrent.id);
      expect(
        adopted.drafts
            .singleWhere((draft) => draft.id == 'draft_shared')
            .state
            .body,
        '账号较新版本',
      );
      expect(
        adopted.drafts
            .singleWhere((draft) => draft.id == sourceCurrent.id)
            .state
            .body,
        '游客当前草稿',
      );
      expect(sourceAfter.drafts, isEmpty);
      expect(sourceAfter.currentId, isNull);
      expect(
        prefs.getKeys().where(
          (key) => key.startsWith('create_drafts:$sourceScope:'),
        ),
        isEmpty,
      );
    });

    test('draft payload survives a missing or corrupt index write', () async {
      final scopeKey = CreateDraftLocalStorage.scopeKeyForUser('user_001');
      final draft = _buildDraft(
        id: 'draft_recovered',
        updatedAtMs: 4000,
        flowKind: CreateDraftFlowKind.article,
        title: '可恢复草稿',
        body: '索引损坏时仍从独立草稿载荷恢复',
      );
      SharedPreferences.setMockInitialValues(<String, Object>{
        CreateDraftLocalStorage.scopedIndexKey(scopeKey): '{invalid-json',
        CreateDraftLocalStorage.scopedDraftPayloadKey(scopeKey, draft.id):
            jsonEncode(draft.toStorageMap()),
      });

      final repository = SharedPreferencesCreateDraftRepository(
        scopeKey: scopeKey,
      );
      final recovered = await repository.load();

      expect(recovered.drafts, hasLength(1));
      expect(recovered.drafts.single.id, draft.id);
      expect(recovered.drafts.single.state.title, '可恢复草稿');
    });
  });
}
