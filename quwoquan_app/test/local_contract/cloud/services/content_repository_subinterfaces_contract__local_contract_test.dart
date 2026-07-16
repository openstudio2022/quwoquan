import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';

void main() {
  group('Content facets 装配契约 (D2a/D2b)', () {
    test('Post Mock 只实现非 Comment 细粒度 Facet', () {
      final repo = MockContentRepository();
      expect(repo, isA<ContentReadRepository>());
      expect(repo, isA<ContentPostDetailReader>());
      expect(repo, isA<ContentAuthorPostsReader>());
      expect(repo, isA<ContentWriteRepository>());
      expect(repo, isA<ContentEngagementRepository>());
      expect(repo, isNot(isA<ContentCommentFacet>()));
      expect(repo, isA<ContentConfigRepository>());
    });

    test('组合根按 facet 装配缓存与直连 adapter', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      // 测试环境（非 release、非 beta/gamma）默认数据源为 mock。
      expect(container.read(appDataSourceModeProvider), AppDataSourceMode.mock);

      final read = container.read(contentReadRepositoryProvider);
      final write = container.read(contentWriteRepositoryProvider);
      final engagement = container.read(contentEngagementRepositoryProvider);
      final config = container.read(contentConfigRepositoryProvider);
      final workBrowserDetail = container.read(
        workBrowserContentPostDetailReaderProvider,
      );
      final userProfilePosts = container.read(
        userProfileContentAuthorPostsReaderProvider,
      );

      expect(write, same(read));
      expect(engagement, same(config));
      expect(engagement, isNot(same(read)));
      expect(workBrowserDetail, isA<ContentPostDetailReader>());
      expect(userProfilePosts, isA<ContentAuthorPostsReader>());
      expect(
        () => container.read(workBrowserContentCommentFacetProvider),
        throwsA(
          predicate<Object>(
            (error) => error.toString().contains(
              'ContentCommentFacet is Remote-only in production composition',
            ),
          ),
        ),
      );
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
