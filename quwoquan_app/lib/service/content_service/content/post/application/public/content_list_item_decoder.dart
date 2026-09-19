import 'package:quwoquan_app/runtime/transport/generated/client_content_presentation_contract.g.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_feed_object_card.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 列表项被隔离的类型化原因；每个成员对应一条 canonical 契约偏差。
enum ContentListItemIsolationReason {
  /// 信封对象种类不在编译期能力闭集内。
  unsupportedObjectKind,

  /// 信封内容类型不在编译期能力闭集内。
  unsupportedContentType,

  /// 信封首页配方不在编译期能力闭集内。
  unsupportedPresentationRecipe,

  /// 信封目的面不在编译期能力闭集内；目的面没有兼容替换。
  unsupportedOpenSurface,

  /// 信封声明的对象种类与随附投影不一致（缺投影或投影错位）。
  missingObjectPayload,

  /// 信封内容类型与 post 投影的权威内容类型冲突。
  contentTypeConflict,
}

/// 单个被隔离项的观测事实；不含 PII，只保留对象标识与偏差原因。
final class ContentListItemIsolation {
  const ContentListItemIsolation({
    required this.reason,
    required this.deliveryIndex,
    this.objectKind,
    this.objectId,
  });

  final ContentListItemIsolationReason reason;

  /// 服务端交付序位；隔离不改变其它项的序位。
  final int deliveryIndex;

  final ListObjectKind? objectKind;
  final String? objectId;

  @override
  String toString() =>
      'ContentListItemIsolation(reason: ${reason.name}, '
      'deliveryIndex: $deliveryIndex, objectKind: ${objectKind?.wireName}, '
      'objectId: $objectId)';
}

/// 一页统一列表的解码结果。
///
/// [posts] 与 [objectCards] 是同一条服务端序列的两个投影：`objectCards` 的
/// `anchorIndex` 指向它在 [posts] 中的插入位，因此重新编织后与交付序位一致。
final class ContentListItemsDecoding {
  const ContentListItemsDecoding({
    required this.posts,
    required this.objectCards,
    required this.isolated,
  });

  static const ContentListItemsDecoding empty = ContentListItemsDecoding(
    posts: <ContentPostViewData>[],
    objectCards: <ContentFeedObjectCard>[],
    isolated: <ContentListItemIsolation>[],
  );

  final List<ContentPostViewData> posts;
  final List<ContentFeedObjectCard> objectCards;
  final List<ContentListItemIsolation> isolated;

  bool get hasIsolatedItems => isolated.isNotEmpty;
}

/// 逐项解码统一列表信封，未知或不支持项就地隔离。
///
/// 只读信封的单一权威字段：`objectKind` 选投影、`openSurface` 定导航、
/// `contentType` 供媒体槽、`presentationRecipe` 选首页卡；不按附件嗅探类型，
/// 不为未知目的面选择替代面。
final class ContentListItemDecoder {
  const ContentListItemDecoder({
    this.postMapper = const ContentPostProjectionMapper(),
    this.declaredContract,
  });

  final ContentPostProjectionMapper postMapper;

  /// 覆盖本次解码所用的能力闭集；`null` 即编译期生成的闭集。
  final ClientContentPresentationContract? declaredContract;

  ClientContentPresentationContract get clientContract =>
      declaredContract ?? compiledContentPresentationContract;

  ContentListItemsDecoding decode(List<ContentListItemProjection> items) {
    if (items.isEmpty) {
      return ContentListItemsDecoding.empty;
    }
    final posts = <ContentPostViewData>[];
    final objectCards = <ContentFeedObjectCard>[];
    final isolated = <ContentListItemIsolation>[];
    final contract = clientContract;
    for (var index = 0; index < items.length; index += 1) {
      final item = items[index];
      final reason =
          _capabilityIsolationReason(item.envelope, contract) ??
          switch (item.envelope.objectKind) {
            ListObjectKind.post => _acceptPost(item, posts),
            ListObjectKind.entityHomepage => _acceptHomepage(
              item,
              objectCards,
              // 交付序位派生：该项之前已接纳的 post 数即它的插入位。
              anchorIndex: posts.length,
            ),
          };
      if (reason == null) {
        continue;
      }
      isolated.add(
        ContentListItemIsolation(
          reason: reason,
          deliveryIndex: index,
          objectKind: item.envelope.objectKind,
          objectId: _objectIdOf(item.envelope),
        ),
      );
    }
    return ContentListItemsDecoding(
      posts: List<ContentPostViewData>.unmodifiable(posts),
      objectCards: List<ContentFeedObjectCard>.unmodifiable(objectCards),
      isolated: List<ContentListItemIsolation>.unmodifiable(isolated),
    );
  }

  /// 接纳成功返回 `null`；否则返回该项的隔离原因。
  ContentListItemIsolationReason? _acceptPost(
    ContentListItemProjection item,
    List<ContentPostViewData> posts,
  ) {
    final projection = item.post;
    if (projection == null) {
      return ContentListItemIsolationReason.missingObjectPayload;
    }
    final envelopeContentType = item.envelope.contentType;
    if (envelopeContentType != null &&
        envelopeContentType != projection.contentType) {
      return ContentListItemIsolationReason.contentTypeConflict;
    }
    posts.add(
      postMapper.toDto(
        projection,
        openSurface: item.envelope.openSurface,
        presentationRecipe: item.envelope.presentationRecipe,
      ),
    );
    return null;
  }

  /// 接纳成功返回 `null`；否则返回该项的隔离原因。
  ContentListItemIsolationReason? _acceptHomepage(
    ContentListItemProjection item,
    List<ContentFeedObjectCard> objectCards, {
    required int anchorIndex,
  }) {
    final homepage = item.homepage;
    if (homepage == null) {
      return ContentListItemIsolationReason.missingObjectPayload;
    }
    objectCards.add(
      ContentFeedObjectCard(
        homepage: homepage,
        openSurface: item.envelope.openSurface,
        anchorIndex: anchorIndex,
      ),
    );
    return null;
  }

  ContentListItemIsolationReason? _capabilityIsolationReason(
    ListItemPresentationEnvelope envelope,
    ClientContentPresentationContract contract,
  ) {
    if (!contract.listObjectKinds.contains(envelope.objectKind)) {
      return ContentListItemIsolationReason.unsupportedObjectKind;
    }
    if (!contract.openSurfaces.contains(envelope.openSurface)) {
      return ContentListItemIsolationReason.unsupportedOpenSurface;
    }
    final contentType = envelope.contentType;
    if (contentType != null && !contract.contentTypes.contains(contentType)) {
      return ContentListItemIsolationReason.unsupportedContentType;
    }
    final recipe = envelope.presentationRecipe;
    if (recipe != null && !contract.presentationRecipes.contains(recipe)) {
      return ContentListItemIsolationReason.unsupportedPresentationRecipe;
    }
    return null;
  }

  String? _objectIdOf(ListItemPresentationEnvelope envelope) =>
      envelope.post?.postId ?? envelope.homepage?.homepageId;
}
