import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_share_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_travelogue_draft.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';

typedef GatheringShareDraftClock = int Function();

/// Circle 隐私快照到 Content 本地文章草稿的边界适配器。
///
/// [publicationContinuationOperationId] 必须来自 Circle generated handoff；
/// 该适配器不读取实时 Gathering/Chat 数据，也不直接发布 Post。
final class GatheringShareDraftWriter
    implements GatheringJourneyTravelogueDraftWriter {
  const GatheringShareDraftWriter({
    required this.repository,
    required this.clock,
    required this.publicationContinuationOperationId,
  });

  final CreateDraftRepository repository;
  final GatheringShareDraftClock clock;
  final String publicationContinuationOperationId;

  @override
  Future<String> save(
    GatheringJourneyTravelogueDraftSource source,
    GatheringJourneyTravelogueDraftContent content,
  ) async {
    final operationId = publicationContinuationOperationId.trim();
    if (operationId.isEmpty) {
      throw StateError(
        'Gathering publication continuation operation must not be blank',
      );
    }
    final nodes = <ArticleDocumentNode>[
      ArticleDocumentNode(
        id: 'document_title',
        type: ArticleDocumentNodeType.documentTitle,
        text: content.title.trim(),
      ),
      for (var index = 0; index < content.blocks.length; index += 1)
        ArticleDocumentNode(
          id: 'gathering_travel_${index + 1}',
          type: _nodeType(content.blocks[index].kind),
          text: content.blocks[index].text.trim(),
        ),
    ];
    final document = ArticleDocumentData(nodes: nodes);
    final pages = buildArticlePagesSnapshotFromDocument(document);
    final isPublic =
        source.visibility == GatheringJourneyShareVisibility.public;
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
        isPublic: isPublic,
        summary: content.summary.trim(),
        entityRefs: isPublic
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
        operationId: operationId,
        sourceEntityRef: source.sourceEntityRef,
      ),
    );
    final stored = await repository.upsertDraft(
      draft,
      currentDraftId: source.localDraftId,
    );
    if (stored.currentDraftId != source.localDraftId ||
        stored.draftById(source.localDraftId) == null) {
      throw StateError('Gathering travelogue draft was not persisted');
    }
    return source.localDraftId;
  }
}

ArticleDocumentNodeType _nodeType(
  GatheringJourneyTravelogueDraftBlockKind kind,
) {
  return switch (kind) {
    GatheringJourneyTravelogueDraftBlockKind.heading =>
      ArticleDocumentNodeType.headingMajor,
    GatheringJourneyTravelogueDraftBlockKind.paragraph =>
      ArticleDocumentNodeType.paragraph,
    GatheringJourneyTravelogueDraftBlockKind.orderedItem =>
      ArticleDocumentNodeType.orderedItem,
    GatheringJourneyTravelogueDraftBlockKind.bulletItem =>
      ArticleDocumentNodeType.bulletItem,
  };
}
