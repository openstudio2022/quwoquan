import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/client_content_presentation_contract.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_decoder.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_post_contract_fixture.dart';

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/
//   unified-presentation-model/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/
//   spec.md#req-005

ContentListItemProjection _postItem({
  required String postId,
  ContentType contentType = ContentType.image,
  ContentUiSurface openSurface = ContentUiSurface.mediaImmersive,
  FeedPresentationRecipe? presentationRecipe =
      FeedPresentationRecipe.coverMediaCard,
  ContentType? envelopeContentType,
  bool withPayload = true,
}) => ContentListItemProjection(
  envelope: ListItemPresentationEnvelope(
    objectKind: ListObjectKind.post,
    contentType: envelopeContentType ?? contentType,
    presentationRecipe: presentationRecipe,
    openSurface: openSurface,
    post: ListItemPostRef(postId: postId),
  ),
  post: withPayload
      ? contentPostProjectionFixture(
          postId: postId,
          contentType: contentType.wireName,
        )
      : null,
);

ContentListItemProjection _homepageItem({
  String homepageId = 'homepage_sight_west_lake',
  ContentUiSurface openSurface = ContentUiSurface.homepageDetail,
  bool withPayload = true,
}) => ContentListItemProjection(
  envelope: ListItemPresentationEnvelope(
    objectKind: ListObjectKind.entityHomepage,
    openSurface: openSurface,
    homepage: ListItemHomepageRef(homepageId: homepageId),
  ),
  homepage: withPayload
      ? HomepageSearchItemView(
          homepageId: homepageId,
          canonicalEntityId: 'entity_sight_west_lake',
          title: '西湖',
          homepageType: HomepageType.sight,
          status: HomepageStatus.published,
          ratingCount: 0,
        )
      : null,
);

/// 能力闭集少于编译期闭集的旧端：只声明 post + mediaImmersive。
final _narrowContract = ClientContentPresentationContract(
  contentTypes: const <ContentType>[ContentType.image],
  listObjectKinds: const <ListObjectKind>[ListObjectKind.post],
  presentationRecipes: const <FeedPresentationRecipe>[
    FeedPresentationRecipe.coverMediaCard,
  ],
  openSurfaces: const <ContentUiSurface>[ContentUiSurface.mediaImmersive],
  contractDigest: 'sha256:'
      '0000000000000000000000000000000000000000000000000000000000000000',
);

void main() {
  group('ContentListItemDecoder — 单字段单责', () {
    test('post 项按信封携带 openSurface 与首页配方，不从内容类型反推', () {
      final decoding = const ContentListItemDecoder().decode(
        <ContentListItemProjection>[
          _postItem(
            postId: 'p1',
            contentType: ContentType.article,
            openSurface: ContentUiSurface.articleReader,
            presentationRecipe: FeedPresentationRecipe.articleExcerptCard,
          ),
        ],
      );

      final post = decoding.posts.single;
      expect(post.id, 'p1');
      expect(post.type, ContentType.article);
      expect(post.openSurface, ContentUiSurface.articleReader);
      expect(post.presentationRecipe, FeedPresentationRecipe.articleExcerptCard);
      expect(decoding.isolated, isEmpty);
    });

    test('实体主页项独立成卡，anchorIndex 取交付序位中前置 post 数', () {
      final decoding = const ContentListItemDecoder().decode(
        <ContentListItemProjection>[
          _postItem(postId: 'p1'),
          _postItem(postId: 'p2'),
          _homepageItem(),
          _postItem(postId: 'p3'),
        ],
      );

      expect(
        decoding.posts.map((post) => post.id),
        <String>['p1', 'p2', 'p3'],
      );
      final card = decoding.objectCards.single;
      expect(card.objectKind, ListObjectKind.entityHomepage);
      expect(card.objectId, 'homepage_sight_west_lake');
      expect(card.openSurface, ContentUiSurface.homepageDetail);
      expect(card.anchorIndex, 2);
      expect(decoding.isolated, isEmpty);
    });
  });

  group('ContentListItemDecoder — 未知项逐项隔离', () {
    test('闭集外目的面只隔离该项，前后已知项保持序位', () {
      final decoding = ContentListItemDecoder(
        declaredContract: _narrowContract,
      ).decode(<ContentListItemProjection>[
        _postItem(postId: 'p1'),
        _postItem(
          postId: 'p2',
          contentType: ContentType.article,
          openSurface: ContentUiSurface.articleReader,
          presentationRecipe: FeedPresentationRecipe.articleExcerptCard,
        ),
        _postItem(postId: 'p3'),
      ]);

      expect(decoding.posts.map((post) => post.id), <String>['p1', 'p3']);
      final isolation = decoding.isolated.single;
      expect(
        isolation.reason,
        ContentListItemIsolationReason.unsupportedOpenSurface,
      );
      expect(isolation.deliveryIndex, 1);
      expect(isolation.objectId, 'p2');
    });

    test('闭集外对象种类不强解 Post 投影', () {
      final decoding = ContentListItemDecoder(
        declaredContract: _narrowContract,
      ).decode(<ContentListItemProjection>[_homepageItem(), _postItem(postId: 'p1')]);

      expect(decoding.objectCards, isEmpty);
      expect(decoding.posts.single.id, 'p1');
      expect(
        decoding.isolated.single.reason,
        ContentListItemIsolationReason.unsupportedObjectKind,
      );
    });

    test('信封声明 post 但缺投影时隔离，不按附件补猜', () {
      final decoding = const ContentListItemDecoder().decode(
        <ContentListItemProjection>[
          _postItem(postId: 'p1', withPayload: false),
          _postItem(postId: 'p2'),
        ],
      );

      expect(decoding.posts.single.id, 'p2');
      expect(
        decoding.isolated.single.reason,
        ContentListItemIsolationReason.missingObjectPayload,
      );
    });

    test('信封内容类型与 post 投影冲突时隔离', () {
      final decoding = const ContentListItemDecoder().decode(
        <ContentListItemProjection>[
          _postItem(
            postId: 'p1',
            contentType: ContentType.image,
            envelopeContentType: ContentType.video,
          ),
        ],
      );

      expect(decoding.posts, isEmpty);
      expect(
        decoding.isolated.single.reason,
        ContentListItemIsolationReason.contentTypeConflict,
      );
    });

    test('全部项被隔离时返回空页，不合成替补对象', () {
      final decoding = ContentListItemDecoder(
        declaredContract: _narrowContract,
      ).decode(<ContentListItemProjection>[_homepageItem(), _homepageItem()]);

      expect(decoding.posts, isEmpty);
      expect(decoding.objectCards, isEmpty);
      expect(decoding.isolated, hasLength(2));
    });
  });

  group('编译期能力闭集', () {
    test('默认闭集即生成常量，摘要与 canonical 规范化字节一致', () {
      expect(
        const ContentListItemDecoder().clientContract,
        same(compiledContentPresentationContract),
      );
      validateClientContentPresentationContract(
        compiledContentPresentationContract,
      );
      expect(
        digestClientContentPresentationContract(
          compiledContentPresentationContract,
        ),
        compiledContentPresentationContractDigest,
      );
    });
  });
}
