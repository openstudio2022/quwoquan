import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentUiSurface, HomepageSearchItemView, ListObjectKind;

/// 列表中的实体主页项。
///
/// 对象事实直接复用 canonical [HomepageSearchItemView]，不另建第二份字段拷贝。
/// [anchorIndex] 是该项在服务端交付序列中的插入位（其前方的 post 数量），由统一
/// 列表序位派生，不是 wire 字段。
final class ContentFeedObjectCard {
  const ContentFeedObjectCard({
    required this.homepage,
    required this.openSurface,
    required this.anchorIndex,
  });

  final HomepageSearchItemView homepage;

  /// 云物化的目的面；端侧导航只读这一个字段。
  final ContentUiSurface openSurface;

  final int anchorIndex;

  ListObjectKind get objectKind => ListObjectKind.entityHomepage;

  String get objectId => homepage.homepageId;

  ContentFeedObjectCard withAnchorIndex(int anchorIndex) =>
      ContentFeedObjectCard(
        homepage: homepage,
        openSurface: openSurface,
        anchorIndex: anchorIndex,
      );

  /// App 本地快照格式；与 HTTP wire 无关，只服务缓存回放。
  Map<String, Object?> toSnapshotMap() => <String, Object?>{
    'homepage': homepage.toWire(),
    'openSurface': openSurface.wireName,
    'anchorIndex': anchorIndex,
  };

  factory ContentFeedObjectCard.fromSnapshotMap(Map<String, Object?> map) {
    final homepage = map['homepage'];
    final anchorIndex = map['anchorIndex'];
    if (homepage is! Map || anchorIndex is! int) {
      throw const FormatException('objectCard snapshot is malformed');
    }
    return ContentFeedObjectCard(
      homepage: HomepageSearchItemView.fromWire(
        Map<String, Object?>.from(homepage),
      ),
      openSurface: ContentUiSurface.fromWire(
        map['openSurface'],
        'ContentFeedObjectCard.openSurface',
      ),
      anchorIndex: anchorIndex,
    );
  }
}
