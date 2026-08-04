import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/content/content/post/mock_content_repository.dart';
import '../../../support/cloud_services/test_content_comment_facet.dart';

void main() {
  group('Content facets 装配契约 (D2a/D2b)', () {
    test('Post Mock 只实现非 Comment 细粒度 Facet', () {
      final repo = MockContentRepository();
      expect(repo, isA<ContentDiscoveryFeedQuery>());
      expect(repo, isA<ContentReadRepository>());
      expect(repo, isA<ContentPostDetailReader>());
      expect(repo, isA<ContentAuthorPostsReader>());
      expect(repo, isA<ContentPostDeleteCommandWriter>());
      expect(repo, isNot(isA<ContentCommentFacet>()));
      expect(repo, isA<ContentConfigRepository>());
    });

    test('组合根按 facet 装配缓存与直连 adapter', () {
      final container = ProviderContainer(
        overrides: [
          ...mockContentFacetOverrides(
            MockContentRepository(),
            commentFacet: TestContentCommentFacet(),
          ),
        ],
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
      expect(
        container.read(workBrowserContentCommentFacetProvider),
        isA<ContentCommentFacet>(),
      );
    });

    test('production content composition 不读取 AppDataSourceMode', () {
      final composition = <String>[
        File(
          'lib/core/providers/app_providers_content_facets.dart',
        ).readAsStringSync(),
        File(
          'lib/core/providers/app_providers_content_extras.dart',
        ).readAsStringSync(),
      ].join('\n');
      final discovery = File(
        'lib/ui/discovery/providers/discovery_feed_provider.dart',
      ).readAsStringSync();

      expect(composition, isNot(contains('appDataSourceModeProvider')));
      expect(composition, isNot(contains('AppDataSourceMode')));
      expect(discovery, contains('contentDiscoveryFeedQueryProvider'));
      expect(discovery, isNot(contains('contentReadRepositoryProvider')));
    });
  });
}
