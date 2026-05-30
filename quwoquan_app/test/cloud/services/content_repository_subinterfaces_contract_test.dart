import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  group('ContentRepository 子接口拆分契约 (D2a/D2b)', () {
    test('Mock 实现同时满足全部 6 个 ≤10 方法子接口', () {
      final repo = MockContentRepository();
      expect(repo, isA<ContentReadRepository>());
      expect(repo, isA<ContentWriteRepository>());
      expect(repo, isA<ContentReactionRepository>());
      expect(repo, isA<ContentCommentRepository>());
      expect(repo, isA<ContentMediaRepository>());
      expect(repo, isA<ContentConfigRepository>());
      expect(repo, isA<ContentRepository>());
    });

    test('子接口 Provider 复用同一 contentRepository 实例', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      // 测试环境（非 release、非 beta/gamma）默认数据源为 mock。
      expect(
        container.read(appDataSourceModeProvider),
        AppDataSourceMode.mock,
      );

      final root = container.read(contentRepositoryProvider);
      expect(container.read(contentReadRepositoryProvider), same(root));
      expect(container.read(contentWriteRepositoryProvider), same(root));
      expect(container.read(contentReactionRepositoryProvider), same(root));
      expect(container.read(contentCommentRepositoryProvider), same(root));
      expect(container.read(contentMediaRepositoryProvider), same(root));
      expect(container.read(contentConfigRepositoryProvider), same(root));
    });
  });

  group('DiscoveryPresentationWire 强类型封装 (R04 de-Map)', () {
    test('typed getter: tags / circleName / visibility', () {
      const wire = DiscoveryPresentationWire(<String, dynamic>{
        'tags': <dynamic>[' 校园 ', '', '摄影'],
        'circleName': '  新东方校友圈 ',
        'visibility': 'circle',
      });
      expect(wire.tags, <String>['校园', '摄影']);
      expect(wire.circleName, '新东方校友圈');
      expect(wire.visibility, 'circle');
    });

    test('缺省值: 空 row → 空标签/空圈名/public', () {
      const wire = DiscoveryPresentationWire(<String, dynamic>{});
      expect(wire.tags, isEmpty);
      expect(wire.circleName, '');
      expect(wire.visibility, 'public');
    });

    test('fromRow(null) 返回 null', () {
      expect(DiscoveryPresentationWire.fromRow(null), isNull);
      expect(
        DiscoveryPresentationWire.fromRow(<String, dynamic>{'tags': <String>[]}),
        isNotNull,
      );
    });

    test('toLegacyRow 透传底层 row（过渡期兼容）', () {
      final row = <String, dynamic>{'shareCount': 9, 'circleName': 'c'};
      final wire = DiscoveryPresentationWire(row);
      expect(wire.toLegacyRow()['shareCount'], 9);
      expect(identical(wire.toLegacyRow(), row), isTrue);
    });
  });
}
