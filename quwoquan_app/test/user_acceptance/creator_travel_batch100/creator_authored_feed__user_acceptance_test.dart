import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

// Phase3 App UAT：batch-100 虚拟创作者经 match_creator 绑定的真实内容，
// 必须能在 alpha mock 发现 feed 中以 batch 作者身份呈现，且作者分散（关注可用）。
const String _batchAuthorPrefix = 'agent_author_travel_travel_batch_100_v1_';

Map<String, dynamic> _loadFixture(String metadataRelativePath) {
  const roots = <String>[
    '../quwoquan_service/contracts/metadata/',
    'quwoquan_service/contracts/metadata/',
    '../../quwoquan_service/contracts/metadata/',
  ];
  for (final root in roots) {
    final file = File('$root$metadataRelativePath');
    if (file.existsSync()) {
      return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    }
  }
  throw StateError(
    'contract fixture 缺失: $metadataRelativePath, cwd=${Directory.current.path}',
  );
}

void main() {
  test('alpha 发现 feed 返回 batch-100 创作者经 match_creator 绑定的文章/图片/视频', () async {
    final scenarios =
        _loadFixture('content/test_fixtures/scenarios/content_scenarios.json');
    final seedSets = scenarios['seedSets'] as Map<String, dynamic>;
    expect(
      seedSets.containsKey('creator_authored_core'),
      isTrue,
      reason: 'creator_authored_core seedSet 必须由 bind-content 物化进 content_scenarios',
    );

    final seedSet = seedSets['creator_authored_core'] as Map<String, dynamic>;
    final rawPosts = (seedSet['posts'] as List)
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
    expect(rawPosts, isNotEmpty);

    final posts = rawPosts.map(postBaseDtoFromMap).toList(growable: false);
    final repo = MockContentRepository(seedPosts: posts);

    final feed = await repo.listDiscoveryFeed(category: 'all', limit: 0);
    final feedIds = feed.map((post) => post.id).toSet();
    for (final post in posts) {
      expect(
        feedIds,
        contains(post.id),
        reason: '${post.id} 应出现在 alpha 发现 feed',
      );
      expect(
        post.authorId,
        startsWith(_batchAuthorPrefix),
        reason: '${post.id} 作者 ${post.authorId} 必须属于 batch-100 创作者池',
      );
    }

    final carriers =
        rawPosts.map((post) => post['contentType'].toString()).toSet();
    expect(
      carriers,
      containsAll(<String>['article', 'image', 'video']),
      reason: '代表性子集必须覆盖文章/图片/视频三种载体',
    );

    // 关注可用：每条内容绑定不同创作者，关注动作分散到不同 batch 作者。
    final authors = posts.map((post) => post.authorId).toSet();
    expect(
      authors.length,
      posts.length,
      reason: '每条内容应绑定到不同的 batch-100 创作者',
    );

    // 单一真相源：内容 seedSet 的作者必须与 binding 种子 (creator_content.seed.json) 一致。
    final binding = _loadFixture(
      '_shared/test_fixtures/creator_pool/creator_content.seed.json',
    );
    final bindingAuthors = (binding['posts'] as List)
        .whereType<Map>()
        .map((post) => post['authorId'].toString())
        .toSet();
    expect(
      authors,
      equals(bindingAuthors),
      reason: 'content_scenarios 的创作者归属必须与 match_creator binding 种子一致（单一真相源）',
    );
  });
}
