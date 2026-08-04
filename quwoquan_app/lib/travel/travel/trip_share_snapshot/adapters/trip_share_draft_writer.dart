import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_travelogue_draft.dart';
import 'package:quwoquan_app/application/content/post/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripShareDraftClock = int Function();

/// Travel 隐私快照到 Content 本地文章草稿的唯一适配器。
///
/// 它不读取 Trip、群聊或媒体服务，也不发布 Post；发布前仍由用户在 Content
/// 编辑器检查、补充素材并确认。
final class TripShareDraftWriter implements TripTravelogueDraftWriter {
  const TripShareDraftWriter({required this.repository, required this.clock});

  final CreateDraftRepository repository;
  final TripShareDraftClock clock;

  @override
  Future<String> save(
    TripTravelogueDraftSource source,
    TripTravelogueDraftContent content,
  ) async {
    final nodes = <ArticleDocumentNode>[
      ArticleDocumentNode(
        id: 'document_title',
        type: ArticleDocumentNodeType.documentTitle,
        text: content.title.trim(),
      ),
      for (var index = 0; index < content.blocks.length; index += 1)
        ArticleDocumentNode(
          id: 'travel_${index + 1}',
          type: _nodeType(content.blocks[index].kind),
          text: content.blocks[index].text.trim(),
        ),
    ];
    final document = ArticleDocumentData(nodes: nodes);
    final pages = buildArticlePagesSnapshotFromDocument(document);
    final state = CreateEditorState.initial().copyWith(
      draftId: source.localDraftId,
      title: document.title,
      body: buildArticlePlainTextFromDocument(document),
      articleDocument: document,
      articlePages: pages,
      activeArticlePageId: pages.first.id,
      activeArticleBlockId: nodes
          .firstWhere((node) => !node.isDocumentTitle)
          .id,
      settings: PublishSettings(
        isPublic: source.visibility == TripShareSnapshotVisibility.public,
        summary: content.summary.trim(),
        entityRefs: source.visibility == TripShareSnapshotVisibility.public
            ? <String>[source.sourceEntityRef]
            : const <String>[],
      ),
    );
    final draft = CreateDraft(
      id: source.localDraftId,
      updatedAtMs: clock(),
      state: state,
      sourceType: 'article',
      publicationContinuation: CreateDraftPublicationContinuationRef(
        operationId: AppCloudOperationIds
            .travelTripPlanContentLinkPutTripPlanContentLink,
        sourceEntityRef: source.sourceEntityRef,
      ),
    );
    final stored = await repository.upsertDraft(
      draft,
      currentDraftId: source.localDraftId,
    );
    if (stored.currentDraftId != source.localDraftId ||
        stored.draftById(source.localDraftId) == null) {
      throw StateError('Travelogue local draft was not persisted');
    }
    return source.localDraftId;
  }
}

ArticleDocumentNodeType _nodeType(TripTravelogueDraftBlockKind kind) {
  return switch (kind) {
    TripTravelogueDraftBlockKind.heading =>
      ArticleDocumentNodeType.headingMajor,
    TripTravelogueDraftBlockKind.paragraph => ArticleDocumentNodeType.paragraph,
    TripTravelogueDraftBlockKind.orderedItem =>
      ArticleDocumentNodeType.orderedItem,
    TripTravelogueDraftBlockKind.bulletItem =>
      ArticleDocumentNodeType.bulletItem,
  };
}
