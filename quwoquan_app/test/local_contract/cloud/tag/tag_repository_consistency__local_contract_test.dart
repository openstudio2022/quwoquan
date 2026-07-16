import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';

/// T2：MockTagRepository 行为契约 + 后端响应字段→前端 DTO 映射一致性（R12/R13）。
///
/// tag-service 的 search / related / search-by-tags / cooccurrence / related-objects
/// 已从 501 落地为只读实现；本测试锁定 Mock 行为类型契约，并用与后端 *View 同构的
/// JSON 验证 fromJson 字段无漂移，防止端云字段名分叉。
void main() {
  final MockTagRepository repo = MockTagRepository();

  group('MockTagRepository 行为契约', () {
    test('listDimensions 返回 18 维度', () async {
      final dims = await repo.listDimensions();
      expect(dims, isNotEmpty);
      expect(dims.first.dimensionId, isNotEmpty);
    });

    test('listChildren 返回中国省级与完整广东/北京二级行政区', () async {
      final provinces = await repo.listChildren(
        TagTaxonomyRefs.chinaAdminRegionRoot,
      );
      expect(provinces, hasLength(34));
      expect(
        provinces.map((p) => p.tagRef),
        contains('${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省'),
      );
      final guangdong = await repo.listChildren(
        '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省',
      );
      expect(guangdong, hasLength(21));
      expect(guangdong.map((c) => c.displayLabel), contains('深圳'));
      expect(guangdong.map((c) => c.displayLabel), contains('云浮'));
      final beijing = await repo.listChildren(
        '${TagTaxonomyRefs.chinaAdminRegionRoot}/北京市',
      );
      expect(beijing, hasLength(16));
      expect(beijing.map((c) => c.displayLabel), contains('朝阳'));
    });

    test('search 按 label 子串过滤并带 score', () async {
      final results = await repo.search('美食');
      expect(results, isNotEmpty);
      expect(results.every((r) => r.tagRef.isNotEmpty), isTrue);
      expect(results.every((r) => r.score >= 0), isTrue);
    });

    test('related 返回相关标签且 cooccurCount 非负', () async {
      final related = await repo.related('Topic/主题/自然风光');
      expect(related, isNotEmpty);
      expect(related.every((r) => r.cooccurCount >= 0), isTrue);
    });

    test('cooccurrence 返回标签对', () async {
      final pairs = await repo.cooccurrence();
      expect(pairs, isNotEmpty);
      expect(
        pairs.every((p) => p.tagA.isNotEmpty && p.tagB.isNotEmpty),
        isTrue,
      );
    });

    test('searchByTags / relatedObjects 返回声明类型', () async {
      expect(
        await repo.searchByTags(['Topic/摄影']),
        isA<List<TagObjectMatch>>(),
      );
      expect(await repo.relatedObjects('u1'), isA<List<RelatedObject>>());
    });

    test('validateRefs 正确分类有效/无效', () async {
      final result = await repo.validateRefs(['Topic/主题/自然风光', 'Topic/不存在']);
      expect(result.valid, contains('Topic/主题/自然风光'));
      expect(result.invalid, contains('Topic/不存在'));
    });
  });

  group('端云 DTO 字段一致性（后端 *View → 前端 fromJson）', () {
    test('TagSearchResult ← TagSearchResultView{tagRef,label,score}', () {
      final v = TagSearchResult.fromJson({
        'tagRef': 'Topic/旅行',
        'label': '旅行',
        'score': 0.5,
      });
      expect(v.tagRef, 'Topic/旅行');
      expect(v.label, '旅行');
      expect(v.score, 0.5);
    });

    test('TagChild ← TagChildView 全字段锁定', () {
      final v = TagChild.fromJson({
        'tagRef': '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省/深圳市',
        'label': '深圳市',
        'displayLabel': '深圳',
        'labelEn': 'Shenzhen',
        'parentTagRef': '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省',
        'depth': 5,
        'hasChildren': false,
        'releaseId': 'admin-2026-06',
        'lifecycleStatus': 'active',
      });
      expect(v.tagRef, '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省/深圳市');
      expect(v.displayLabel, '深圳');
      expect(v.parentTagRef, '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省');
      expect(v.depth, 5);
      expect(v.hasChildren, isFalse);
      expect(v.releaseId, 'admin-2026-06');
      expect(v.lifecycleStatus, 'active');
    });

    test('RelatedTag ← RelatedTagView{tagRef,label,cooccurCount}', () {
      final v = RelatedTag.fromJson({
        'tagRef': 'Topic/摄影',
        'label': '摄影',
        'cooccurCount': 2,
      });
      expect(v.tagRef, 'Topic/摄影');
      expect(v.cooccurCount, 2);
    });

    test(
      'TagObjectMatch ← TagObjectMatchView{objectId,objectType,matchedTags,score}',
      () {
        final v = TagObjectMatch.fromJson({
          'objectId': 'u1',
          'objectType': 'user',
          'matchedTags': ['Topic/摄影', 'Topic/旅行'],
          'score': 1.0,
        });
        expect(v.objectId, 'u1');
        expect(v.objectType, 'user');
        expect(v.matchedTags, hasLength(2));
        expect(v.score, 1.0);
      },
    );

    test('TagCooccurrence ← TagCooccurrenceView{tagA,tagB,cooccurCount}', () {
      final v = TagCooccurrence.fromJson({
        'tagA': 'Topic/摄影',
        'tagB': 'Entity/机构/学校/北京大学',
        'cooccurCount': 2,
      });
      expect(v.tagA, 'Topic/摄影');
      expect(v.tagB, 'Entity/机构/学校/北京大学');
      expect(v.cooccurCount, 2);
    });

    test(
      'RelatedObject ← RelatedObjectView{objectId,objectType,sharedTags,sharedCount}',
      () {
        final v = RelatedObject.fromJson({
          'objectId': 'u2',
          'objectType': 'user',
          'sharedTags': ['Topic/摄影', 'Entity/机构/学校/北京大学'],
          'sharedCount': 2,
        });
        expect(v.objectId, 'u2');
        expect(v.sharedTags, hasLength(2));
        expect(v.sharedCount, 2);
      },
    );
  });
}
