import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
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

void main() {
  group('create_local_draft_repository', () {
    setUp(() {
      SharedPreferences.setMockInitialValues(<String, Object>{});
    });

    test('local_draft_repository_preserves_flow_kind_and_order', () async {
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
      final priorImageMap = imageDraft.toStorageMap()..remove('draftFlowKind');

      SharedPreferences.setMockInitialValues(<String, Object>{
        CreateDraftLocalStorage.draftsKey: jsonEncode(<Object?>[
          articleDraft.toStorageMap(),
          priorImageMap,
        ]),
        CreateDraftLocalStorage.currentDraftIdKey: 'draft_image',
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
      expect(prefs.getString(CreateDraftLocalStorage.draftsKey), isNull);
      expect(
        prefs.getString(CreateDraftLocalStorage.currentDraftIdKey),
        isNull,
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
