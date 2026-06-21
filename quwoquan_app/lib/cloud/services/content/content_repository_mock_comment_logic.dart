part of 'content_repository.dart';

// MockContentRepository 的评论域逻辑（评论种子 / 计数派生 / 排序 / 综合分 / delta 窗口）。
// 与 content_repository_mock.dart 同库（part），共享私有实例状态 commentsStub；
// 拆出仅为收敛主文件行数（R03），不构成第二数据源（R15/R24）。

/// 一级评论随列表返回的二级回复预览数（对齐 contract
/// `sys.content.comment.reply_preview_count` 默认值）。
const int _mockReplyPreviewCount = 1;

const String _highFidelityCommentSourcePostId = 'fixture_photo_001';
const Map<String, String> _commentSourcePostIds = <String, String>{
  // 首页 showcase 首图复用 contract 高保评论集合，避免卡片显示 19 条、
  // 评论页只落到 showcase 自带 3 条轻样本。
  'alpha_moment_grid_1': _highFidelityCommentSourcePostId,
};

/// 发现流分页会把基础帖克隆为 `<base>_(photo|video|article)_<n>`（见
/// `ContentMockData._expandDiscoveryFeed`）。克隆帖与基础帖内容同源，归一逻辑把
/// 克隆 id 收敛到基础 id，使其复用同一份 contract 评论种子，避免扩展帖评论区空白。
/// 仅当该 postId 自身无种子评论时回退，不引入第二份 mock 数据源。
final RegExp _discoveryClonePostIdSuffix = RegExp(
  r'_(photo|video|article)_\d+$',
);

List<CommentDto> _contractSeedComments() {
  final comments = <CommentDto>[];
  for (final ref in const <String>[
    'content_discovery_core',
    'comment_thread_core',
    'home_showcase_core',
  ]) {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(ref);
    final raw = seed?['comments'];
    if (raw is! List) {
      continue;
    }
    comments.addAll(
      raw.whereType<Map>().map(
        (item) => CommentDto.fromMap(item.cast<String, dynamic>()),
      ),
    );
  }
  final byId = <String, CommentDto>{};
  for (final comment in comments) {
    byId[comment.id] = comment;
  }
  return byId.values.toList(growable: false);
}

/// 把端侧字符串形态的 personaContextVersion 收敛为云侧 int64 wire（与
/// content-service handler 的 asInt64Flexible 行为一致）。空/非数字 → null。
int? _personaContextVersionToInt(String? raw) {
  final trimmed = raw?.trim() ?? '';
  if (trimmed.isEmpty) return null;
  return int.tryParse(trimmed);
}

/// 半开区间判定 `(since, watermark]`：`since` 为 null 表示首同步（无下界）。
bool _withinHalfOpenWindow(
  DateTime point,
  DateTime? since,
  DateTime watermark,
) {
  if (point.isAfter(watermark)) {
    return false; // point <= watermark
  }
  if (since == null) {
    return true; // 无下界
  }
  return point.isAfter(since); // point > since
}

extension _MockContentCommentLogic on MockContentRepository {
  String _resolveSeededCommentPostId(String postId) {
    final normalized = postId.trim();
    final explicitSource = _commentSourcePostIds[normalized];
    if (explicitSource != null) {
      return explicitSource;
    }
    final hasOwn = commentsStub.any((comment) => comment.postId == normalized);
    if (hasOwn) {
      return normalized;
    }
    final base = normalized.replaceFirst(_discoveryClonePostIdSuffix, '');
    if (base != normalized &&
        commentsStub.any((comment) => comment.postId == base)) {
      return base;
    }
    return normalized;
  }

  /// 计数单一真相源：commentCount 始终由评论集派生（含 0），不再回退 fixture 声明值。
  /// 与 fixture 全局自洽（声明 == 评论集合并计数）及 feed/详情/缓存同源，杜绝第二真相源。
  int _liveCommentCountForPost(String postId) {
    final resolvedPostId = _resolveSeededCommentPostId(postId);
    var totalCount = 0;
    for (final comment in commentsStub) {
      if (comment.postId != resolvedPostId) {
        continue;
      }
      if (comment.status == 'deleted') {
        continue;
      }
      totalCount++;
    }
    return totalCount;
  }

  PostBaseDto _withLiveCommentCount(PostBaseDto post) {
    final totalCount = _liveCommentCountForPost(post.id);
    if (totalCount == post.commentCount) {
      return post;
    }
    // PostBaseDto.toMap() 把 intersectionReasons 等嵌套投影 DTO 原样保留为对象，
    // 直接回环 postBaseDtoFromMap 会被 _parseProjectionDtoList 丢弃（交集线索变空）。
    // 用共享序列化真相源 intersectionReasonsToWireList 下沉为 map，保证计数刷新无损。
    final rebuilt = <String, dynamic>{
      ...post.toMap(),
      'postId': post.id,
      'commentCount': totalCount,
    };
    final reasons = post.intersectionReasons;
    if (reasons != null) {
      rebuilt['intersectionReasons'] = intersectionReasonsToWireList(reasons);
    }
    return postBaseDtoFromMap(rebuilt);
  }

  Map<String, dynamic> _withLiveCommentCountWire(Map<String, dynamic> wire) {
    final postId =
        wire['postId']?.toString() ??
        wire['_id']?.toString() ??
        wire['id']?.toString() ??
        '';
    final totalCount = _liveCommentCountForPost(postId);
    return <String, dynamic>{...wire, 'commentCount': totalCount};
  }

  /// 为一级评论补齐 `replyPreview` / `replyCount` / `replyNextCursor`，与云侧
  /// 列表接口同源：默认随列表回显 1 条二级回复，余量通过游标展开。
  CommentDto _withReplyPreview(String postId, CommentDto comment) {
    final replies =
        commentsStub
            .where(
              (item) =>
                  item.postId == postId &&
                  item.parentCommentId == comment.id &&
                  item.status != 'deleted',
            )
            .toList(growable: false)
          ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    if (replies.isEmpty) {
      return comment.copyWith(
        replyCount: 0,
        replyPreview: const <CommentDto>[],
        replyNextCursor: () => null,
      );
    }
    final previewEnd = _mockReplyPreviewCount.clamp(0, replies.length);
    return comment.copyWith(
      replyCount: replies.length,
      replyPreview: replies.sublist(0, previewEnd),
      replyNextCursor: () => previewEnd < replies.length ? '$previewEnd' : null,
    );
  }

  /// 评论排序与云侧 `sortCommentsByMode` 同源：置顶始终最前（多置顶按 pinnedAt 倒序），
  /// 其余按模式排序。三种模式（综合/最新/最多赞）返回同一集合、同一总数，仅顺序不同。
  /// 综合分用单一 `now` 一次性预计算（消除按 `DateTime.now()` 每次比较的漂移）。
  List<CommentDto> _sortComments(List<CommentDto> comments, String sort) {
    final now = DateTime.now().toUtc();
    final scoreById = <String, double>{
      for (final c in comments) c.id: _commentRecommendedScore(c, now),
    };
    int byMode(CommentDto a, CommentDto b) {
      switch (sort) {
        case 'latest':
          return b.createdAt.compareTo(a.createdAt);
        case 'most_liked':
          final byLike = b.likeCount.compareTo(a.likeCount);
          return byLike != 0 ? byLike : b.createdAt.compareTo(a.createdAt);
        case 'recommended':
        default:
          final byScore = (scoreById[b.id] ?? 0).compareTo(
            scoreById[a.id] ?? 0,
          );
          return byScore != 0 ? byScore : b.createdAt.compareTo(a.createdAt);
      }
    }

    final pinned = <CommentDto>[];
    final rest = <CommentDto>[];
    for (final c in comments) {
      (c.isPinned ? pinned : rest).add(c);
    }
    pinned.sort((a, b) {
      final pa = a.pinnedAt ?? a.createdAt;
      final pb = b.pinnedAt ?? b.createdAt;
      final byPinned = pb.compareTo(pa);
      return byPinned != 0 ? byPinned : byMode(a, b);
    });
    rest.sort(byMode);
    return <CommentDto>[...pinned, ...rest];
  }

  /// 综合分（与云侧 `commentRecommendedScoreAt` 同源）：Wilson 赞/踩下界质量 +
  /// log1p 互动热度 + 48h 半衰期新鲜度衰减。优先使用云侧已落库的 `recommendedScore`，
  /// 缺失时本地按同一公式派生，保证端云同源。
  double _commentRecommendedScore(CommentDto c, DateTime now) {
    final stored = c.recommendedScore;
    if (stored != null && stored != 0) {
      return stored;
    }
    final likes = c.likeCount;
    final dislikes = c.dislikeCount;
    final replies = c.replyCount;
    final quality = _wilsonLowerBound(likes, likes + dislikes);
    final engagement =
        math.log(1 + math.max(likes, 0)) * 12.0 +
        math.log(1 + math.max(replies, 0)) * 8.0;
    final ageHours = now.difference(c.createdAt).inMinutes / 60.0;
    final freshness = 30.0 * math.exp(-(ageHours < 0 ? 0 : ageHours) / 48.0);
    return quality * 60.0 + engagement + freshness;
  }

  double _wilsonLowerBound(int positive, int total) {
    if (total <= 0 || positive < 0) return 0;
    final n = total.toDouble();
    final phat = positive / n;
    const z = 1.96;
    final denom = 1 + z * z / n;
    final centre = phat + z * z / (2 * n);
    final margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n);
    final lower = (centre - margin) / denom;
    return lower < 0 ? 0 : lower;
  }
}
