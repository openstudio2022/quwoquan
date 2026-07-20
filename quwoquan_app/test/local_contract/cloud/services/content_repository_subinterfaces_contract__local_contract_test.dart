import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';

void main() {
  group('Content facets 装配契约 (D2a/D2b)', () {
    test('Post Mock 只实现非 Comment 细粒度 Facet', () {
      final repo = MockContentRepository();
      expect(repo, isA<ContentDiscoveryFeedQuery>());
      expect(repo, isA<ContentReadRepository>());
      expect(repo, isA<ContentPostDetailReader>());
      expect(repo, isA<ContentAuthorPostsReader>());
      expect(repo, isA<ContentWriteRepository>());
      expect(repo, isA<ContentEngagementRepository>());
      expect(repo, isNot(isA<ContentCommentFacet>()));
      expect(repo, isA<ContentConfigRepository>());
    });

    test('组合根按 facet 装配缓存与直连 adapter', () {
      final container = ProviderContainer(
        overrides: [...mockContentFacetOverrides(MockContentRepository())],
      );
      addTearDown(container.dispose);

      final feed = container.read(contentDiscoveryFeedQueryProvider);
      final write = container.read(contentWriteRepositoryProvider);
      final engagement = container.read(contentEngagementRepositoryProvider);
      final config = container.read(contentConfigRepositoryProvider);
      final workBrowserDetail = container.read(
        workBrowserContentPostDetailReaderProvider,
      );
      final userProfilePosts = container.read(
        userProfileContentAuthorPostsReaderProvider,
      );

      expect(feed, isA<ContentDiscoveryFeedQuery>());
      expect(write, isA<ContentWriteRepository>());
      expect(engagement, isA<ContentEngagementRepository>());
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

  group('DiscoveryPresentationWire 强类型封装 (R04 de-Map)', () {
    test('typed getter: tags / visibility', () {
      const wire = DiscoveryPresentationWire(<String, dynamic>{
        'tagRefs': <dynamic>[' 校园 ', '', '摄影'],
        'visibility': 'private',
      });
      expect(wire.tagRefs, <String>['校园', '摄影']);
      expect(wire.visibility, 'private');
    });

    test('缺省值: 空 row → 空标签/public', () {
      const wire = DiscoveryPresentationWire(<String, dynamic>{});
      expect(wire.tagRefs, isEmpty);
      expect(wire.visibility, 'public');
    });

    test('fromRow(null) 返回 null', () {
      expect(DiscoveryPresentationWire.fromRow(null), isNull);
      expect(
        DiscoveryPresentationWire.fromRow(<String, dynamic>{
          'tagRefs': <String>[],
        }),
        isNotNull,
      );
    });

    test('toWireMap 透传底层 canonical wire row 给统一映射器', () {
      final row = <String, dynamic>{'shareCount': 9};
      final wire = DiscoveryPresentationWire(row);
      expect(wire.toWireMap()['shareCount'], 9);
      expect(identical(wire.toWireMap(), row), isTrue);
    });
  });
}
