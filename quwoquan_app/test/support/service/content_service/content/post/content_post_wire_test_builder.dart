/// 为 generated-client 边界测试构造最小 Post read-model wire。
///
/// 该 builder 只属于 content/post，不承载跨域 named example 或场景矩阵。
List<Map<String, Object?>> contentPostReadModelWireExamples() {
  const specs = <({String id, String type, String authorId, String title})>[
    (
      id: 'fixture_photo_001',
      type: 'image',
      authorId: 'fixture_user_photo',
      title: '西湖晨光摄影测试详情',
    ),
    (
      id: 'fixture_photo_002',
      type: 'image',
      authorId: 'fixture_user_photo',
      title: '城市傍晚的光影层次',
    ),
    (
      id: 'fixture_video_001',
      type: 'video',
      authorId: 'fixture_user_travel',
      title: '杭州一日游契约视频',
    ),
    (
      id: 'fixture_article_001',
      type: 'article',
      authorId: 'fixture_user_article',
      title: '契约驱动的发现页文章',
    ),
    (
      id: 'fixture_moment_001',
      type: 'micro',
      authorId: 'fixture_user_current',
      title: '契约周末早餐',
    ),
    (
      id: 'fixture_post_photography_001',
      type: 'image',
      authorId: 'fixture_user_photo',
      title: '晨光摄影',
    ),
    (
      id: 'fixture_post_lifestyle_001',
      type: 'image',
      authorId: 'fixture_user_current',
      title: '窗边生活',
    ),
    (
      id: 'fixture_video_002',
      type: 'video',
      authorId: 'fixture_user_travel',
      title: '城市夜游契约视频',
    ),
    (
      id: 'fixture_moment_002',
      type: 'micro',
      authorId: 'fixture_user_current',
      title: '午后散步契约动态',
    ),
    (
      id: 'fixture_moment_003',
      type: 'micro',
      authorId: 'fixture_user_current',
      title: '周末读书契约动态',
    ),
  ];
  return List<Map<String, Object?>>.generate(specs.length, (index) {
    final spec = specs[index];
    final mediaBase = 'media/image/s/archived-image/post/${spec.id}/v1';
    final authorName = switch (spec.authorId) {
      'fixture_user_photo' => '契约摄影师',
      'fixture_user_travel' => '契约旅行家',
      'fixture_user_article' => '契约撰稿人',
      _ => '测试用户',
    };
    return <String, Object?>{
      'postId': spec.id,
      'contentType': spec.type,
      'contentIdentity': spec.type == 'micro' ? 'moment' : 'work',
      'authorId': spec.authorId,
      'authorDisplayName': authorName,
      'authorAvatarUrl':
          'media/avatar/s/archived-avatar/user/${spec.authorId}/v1/avatar.png',
      'title': spec.title,
      'summary': '对象级 Post 样本 ${index + 1}',
      'body': '对象级 Post 正文 ${index + 1}',
      'coverUrl': '$mediaBase/cover.png',
      'thumbnailUrl': '$mediaBase/cover.png',
      'mediaUrls': <String>['$mediaBase/cover.png'],
      'likeCount': 80 + index,
      'commentCount': index,
      'shareCount': index,
      'width': 1280,
      'height': 960,
      if (spec.type == 'video')
        'videoUrl':
            'media/video/s/video-primary-0001/post/${spec.id}/v1/source.mp4',
      if (spec.type == 'video') 'durationMs': 45000,
      'createdAt': '2026-05-01T0$index:00:00Z',
      'updatedAt': '2026-05-01T0$index:00:00Z',
      'publishedAt': '2026-05-02T0$index:00:00Z',
    };
  }, growable: false);
}

Map<String, Object?> contentDiscoveryWireExample() => <String, Object?>{
  'posts': contentPostReadModelWireExamples(),
};
