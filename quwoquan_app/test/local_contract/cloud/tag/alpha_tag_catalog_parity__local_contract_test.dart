// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';

void main() {
  late AlphaTagFacet query;

  setUp(() {
    query = AlphaTagFacet();
  });

  group('Alpha TagCatalog 与 Remote 查询语义对等', () {
    test('目录和解析只返回 immutable fixture 中存在的 canonical tag', () async {
      final provinces = await query.listChildren(
        TagTaxonomyRefs.chinaAdminRegionRoot,
      );
      expect(provinces, hasLength(34));

      final shenzhenRef = '${TagTaxonomyRefs.chinaAdminRegionRoot}/广东省/深圳市';
      final resolved = await query.resolveTag(shenzhenRef);
      expect(resolved.tagRef, shenzhenRef);
      expect(resolved.label, '深圳');
      expect(resolved.group, 'Topic');
    });

    test('不存在的 tag 显式失败，不合成兜底标签', () async {
      await expectLater(
        query.resolveTag('Topic/不存在'),
        throwsA(
          isA<StateError>().having(
            (error) => error.message,
            'message',
            'TAG.USER.tag_not_found',
          ),
        ),
      );
      await expectLater(
        query.listChildren('Topic/不存在'),
        throwsA(
          isA<StateError>().having(
            (error) => error.message,
            'message',
            'TAG.USER.tag_not_found',
          ),
        ),
      );
      expect(
        await query.listChildren('Topic/主题/自然风光'),
        isEmpty,
        reason: '已存在的叶节点与未知 parent 必须区分',
      );
    });

    test('校验结果绑定 taxonomy release，过期 release 不伪装成功', () async {
      const validRef = 'Topic/主题/自然风光';
      final accepted = await query.validateRefs(
        expectedTaxonomyReleaseId: query.taxonomyReleaseId,
        tagRefs: const <String>[validRef],
      );
      expect(accepted.taxonomyReleaseId, query.taxonomyReleaseId);
      expect(accepted.valid, const <String>[validRef]);
      expect(accepted.invalid, isEmpty);

      final rejected = await query.validateRefs(
        expectedTaxonomyReleaseId: '${query.taxonomyReleaseId}-stale',
        tagRefs: const <String>[validRef],
      );
      expect(rejected.taxonomyReleaseId, query.taxonomyReleaseId);
      expect(rejected.valid, isEmpty);
      expect(rejected.invalid, const <String>[validRef]);
    });
  });
}
