import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

void main() {
  group('Content Post facets 装配契约 (D2a/D2b)', () {
    test('Post Mock 只实现非 Comment 细粒度 Facet', () {
      final repo = MockContentRepository();
      expect(repo, isA<ContentDiscoveryFeedQuery>());
      expect(repo, isA<ContentPostDetailReader>());
      expect(repo, isA<ContentAuthorPostsReader>());
      expect(repo, isA<ContentPostDeleteCommandWriter>());
      expect(repo, isNot(isA<ContentCommentFacet>()));
      expect(repo, isA<ContentConfigRepository>());
    });

    test('组合根按 Post facet 装配缓存与直连 adapter', () {
      final container = ProviderContainer(
        overrides: [...mockContentFacetOverrides(MockContentRepository())],
      );
      addTearDown(container.dispose);

      final feed = container.read(contentDiscoveryFeedQueryProvider);
      final write = container.read(contentPostDeleteCommandWriterProvider);
      final config = container.read(contentConfigRepositoryProvider);
      final workBrowserDetail = container.read(
        workBrowserContentPostDetailReaderProvider,
      );
      final userProfilePosts = container.read(
        userProfileContentAuthorPostsReaderProvider,
      );

      expect(feed, isA<ContentDiscoveryFeedQuery>());
      expect(write, isA<ContentPostDeleteCommandWriter>());
      expect(config, isA<ContentConfigRepository>());
      expect(workBrowserDetail, isA<ContentPostDetailReader>());
      expect(userProfilePosts, isA<ContentAuthorPostsReader>());
    });

    test('production content composition 不读取 AppDataSourceMode', () {
      final composition = <String>[
        File(
          'lib/runtime/di/app_providers_content_facets.dart',
        ).readAsStringSync(),
        File(
          'lib/runtime/di/app_providers_content_extras.dart',
        ).readAsStringSync(),
      ].join('\n');
      final discovery = File(
        'lib/service/content_service/content/post/application/discovery_feed_provider.dart',
      ).readAsStringSync();

      expect(composition, isNot(contains('appDataSourceModeProvider')));
      expect(composition, isNot(contains('AppDataSourceMode')));
      expect(composition, isNot(contains('ContentReadRepository')));
      expect(composition, isNot(contains('RemoteContentRepository')));
      expect(discovery, contains('contentDiscoveryFeedQueryProvider'));
      expect(discovery, isNot(contains('contentReadRepositoryProvider')));
    });
  });
}
