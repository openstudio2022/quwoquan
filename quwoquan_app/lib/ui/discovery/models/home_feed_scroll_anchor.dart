import 'dart:collection';

import 'package:flutter/foundation.dart';

/// 首页 feed 条目的稳定身份。
///
/// 该身份只用于端侧 element/滚动锚点，不替代服务端 cursor 或推荐窗口身份。
String homeFeedPostEntryIdentity(String postId) {
  return 'post:${postId.trim()}';
}

bool homeFeedIsPostEntryIdentity(String stableEntryIdentity) {
  return stableEntryIdentity.startsWith('post:') &&
      stableEntryIdentity.length > 'post:'.length;
}

String homeFeedObjectCardEntryIdentity({
  required String objectKind,
  required String objectId,
  required int anchorIndex,
}) {
  return 'object:${objectKind.trim()}:${objectId.trim()}:$anchorIndex';
}

String homeFeedEntryElementKey(String stableEntryIdentity) {
  return 'home-feed-entry-$stableEntryIdentity';
}

@immutable
class HomeFeedScrollAnchor {
  const HomeFeedScrollAnchor({
    required this.channelId,
    required this.stableEntryIdentity,
    required this.entryIndex,
    required this.scrollOffset,
    required this.viewportOffset,
    required this.capturedAt,
  });

  final String channelId;
  final String stableEntryIdentity;
  final int entryIndex;

  /// 保存锚点时 viewport 的绝对滚动 offset，仅用于首帧粗定位。
  final double scrollOffset;

  /// 锚点条目顶部相对 viewport 顶部的位置，用于布局后精确校正。
  final double viewportOffset;
  final DateTime capturedAt;
}

/// 容器作用域、LRU 有界的频道滚动锚点。
///
/// 仅保留小型定位元数据，不持有 Widget、BuildContext、Post 或媒体资源。
class HomeFeedScrollAnchorStore {
  HomeFeedScrollAnchorStore({this.maxChannels = 8}) : assert(maxChannels > 0);

  final int maxChannels;
  final LinkedHashMap<String, HomeFeedScrollAnchor> _anchors =
      LinkedHashMap<String, HomeFeedScrollAnchor>();

  void save(HomeFeedScrollAnchor anchor) {
    final channelId = anchor.channelId.trim();
    final identity = anchor.stableEntryIdentity.trim();
    if (channelId.isEmpty || identity.isEmpty) {
      return;
    }
    _anchors.remove(channelId);
    _anchors[channelId] = anchor;
    while (_anchors.length > maxChannels) {
      _anchors.remove(_anchors.keys.first);
    }
  }

  /// 只有锚点条目仍在当前 resident window 时才允许恢复。
  ///
  /// 条目已被刷新替换或尚未从持久 QuerySnapshot/双向 cursor 回填时返回 null，
  /// 禁止用过期 pixel offset 跳到另一条内容。
  HomeFeedScrollAnchor? readRestorable(
    String channelId, {
    required Set<String> residentEntryIdentities,
  }) {
    final normalized = channelId.trim();
    final anchor = _anchors.remove(normalized);
    if (anchor == null) {
      return null;
    }
    _anchors[normalized] = anchor;
    if (!residentEntryIdentities.contains(anchor.stableEntryIdentity)) {
      return null;
    }
    return anchor;
  }

  HomeFeedScrollAnchor? peek(String channelId) {
    return _anchors[channelId.trim()];
  }

  void remove(String channelId) {
    _anchors.remove(channelId.trim());
  }

  int get count => _anchors.length;

  @visibleForTesting
  List<String> get channelIds => List<String>.unmodifiable(_anchors.keys);
}
