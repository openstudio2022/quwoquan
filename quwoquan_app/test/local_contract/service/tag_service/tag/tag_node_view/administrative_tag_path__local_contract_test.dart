import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/geo_tag_ref_resolver.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/administrative_tag_path.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 对象级 typed double：只认注册过的 tagRef，其余按 tag-service 的
/// `TAG.USER.tag_not_found` 语义抛出。
final class _TagCatalogDouble implements TagCatalogQuery {
  _TagCatalogDouble(this.known);

  final Set<String> known;
  final List<String> resolveCalls = <String>[];

  @override
  Future<TagResolveView> resolveTag(String tagRef) async {
    resolveCalls.add(tagRef);
    if (!known.contains(tagRef)) {
      throw StateError('TAG.USER.tag_not_found: $tagRef');
    }
    return TagResolveView(
      tagRef: tagRef,
      group: 'Topic',
      label: tagRef.split('/').last,
    );
  }

  @override
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = 50,
  }) => throw UnimplementedError();

  @override
  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) => throw UnimplementedError();
}

void main() {
  group('parseChineseAdministrativeChain', () {
    test('省 / 市 / 区三级地址', () {
      expect(parseChineseAdministrativeChain('浙江省杭州市西湖区北山街道1号'), <String>[
        '浙江省',
        '杭州市',
        '西湖区',
      ]);
    });

    test('直辖市跳过地级市层，与标签树形状一致', () {
      expect(parseChineseAdministrativeChain('北京市东城区东华门街道'), <String>[
        '北京市',
        '东城区',
      ]);
      expect(parseChineseAdministrativeChain('上海市黄浦区南京东路'), <String>[
        '上海市',
        '黄浦区',
      ]);
    });

    test('自治区与自治州', () {
      expect(parseChineseAdministrativeChain('新疆维吾尔自治区伊犁哈萨克自治州昭苏县'), <String>[
        '新疆维吾尔自治区',
        '伊犁哈萨克自治州',
        '昭苏县',
      ]);
    });

    test('县级市与旗', () {
      expect(parseChineseAdministrativeChain('浙江省温州市瑞安市'), <String>[
        '浙江省',
        '温州市',
        '瑞安市',
      ]);
      expect(parseChineseAdministrativeChain('内蒙古自治区呼伦贝尔市陈巴尔虎旗'), <String>[
        '内蒙古自治区',
        '呼伦贝尔市',
        '陈巴尔虎旗',
      ]);
    });

    test('带国名前缀与只到市级的地址', () {
      expect(parseChineseAdministrativeChain('中国四川省成都市'), <String>[
        '四川省',
        '成都市',
      ]);
    });

    test('无法识别行政区时返回空，不臆造', () {
      expect(parseChineseAdministrativeChain(''), isEmpty);
      expect(parseChineseAdministrativeChain('   '), isEmpty);
      expect(parseChineseAdministrativeChain('Shibuya, Tokyo'), isEmpty);
    });
  });

  group('administrativeTagRefCandidates', () {
    test('候选由细到粗且都挂在行政区根下', () {
      final candidates = administrativeTagRefCandidatesFromAddress(
        '浙江省杭州市西湖区北山街道1号',
      );

      expect(candidates, <String>[
        '$kAdministrativeTagRoot/中国/浙江省/杭州市/西湖区',
        '$kAdministrativeTagRoot/中国/浙江省/杭州市',
        '$kAdministrativeTagRoot/中国/浙江省',
        '$kAdministrativeTagRoot/中国',
      ]);
    });

    test('可指定国家用于境外地址', () {
      expect(
        administrativeTagRefCandidates(<String>['清迈府'], country: '泰国'),
        <String>[
          '$kAdministrativeTagRoot/泰国/清迈府',
          '$kAdministrativeTagRoot/泰国',
        ],
      );
    });
  });

  group('境外地址解析', () {
    test('日本按都道府县 + 区市切段', () {
      expect(
        administrativeTagRefCandidatesFromAddress('日本东京都新宿区西新宿2-8-1'),
        <String>[
          '$kAdministrativeTagRoot/日本/东京都/新宿区',
          '$kAdministrativeTagRoot/日本/东京都',
          '$kAdministrativeTagRoot/日本',
        ],
      );
      expect(
        administrativeTagRefCandidatesFromAddress('日本北海道札幌市中央区'),
        contains('$kAdministrativeTagRoot/日本/北海道/札幌市'),
      );
    });

    test('泰国按府 + 市镇切段', () {
      expect(administrativeTagRefCandidatesFromAddress('泰国清迈府清迈市塔佩路'), <String>[
        '$kAdministrativeTagRoot/泰国/清迈府/清迈市',
        '$kAdministrativeTagRoot/泰国/清迈府',
        '$kAdministrativeTagRoot/泰国',
      ]);
    });

    test('韩国按广域市/道 + 区切段', () {
      expect(administrativeTagRefCandidatesFromAddress('韩国釜山广域市海云台区'), <String>[
        '$kAdministrativeTagRoot/韩国/釜山广域市/海云台区',
        '$kAdministrativeTagRoot/韩国/釜山广域市',
        '$kAdministrativeTagRoot/韩国',
      ]);
    });

    test('无层级词约定的国家只产出国家级候选，不按空格瞎切', () {
      expect(
        administrativeTagRefCandidatesFromAddress('美国加利福尼亚州旧金山市场街'),
        <String>['$kAdministrativeTagRoot/美国'],
      );
    });

    test('境外国名优先于中国规则，日本的县不被吃成中国省级', () {
      final candidates = administrativeTagRefCandidatesFromAddress('日本冲绳县那霸市');
      expect(candidates.first, startsWith('$kAdministrativeTagRoot/日本/'));
      expect(
        candidates.every((c) => !c.startsWith('$kAdministrativeTagRoot/中国')),
        isTrue,
      );
    });

    test('未收录的国家不产出 geoTagRef', () {
      expect(administrativeTagRefCandidatesFromAddress('冈比亚班珠尔某街'), isEmpty);
    });
  });

  group('GeoTagRefResolver', () {
    test('命中最具体的区县标签，且不再尝试更粗的候选', () async {
      final catalog = _TagCatalogDouble(<String>{
        '$kAdministrativeTagRoot/中国/浙江省/杭州市/西湖区',
        '$kAdministrativeTagRoot/中国/浙江省/杭州市',
      });

      final resolved = await GeoTagRefResolver(
        catalog,
      ).resolveFromPoi(address: '浙江省杭州市西湖区北山街道1号');

      expect(resolved, '$kAdministrativeTagRoot/中国/浙江省/杭州市/西湖区');
      expect(catalog.resolveCalls, hasLength(1));
    });

    test('标签树未覆盖到区县时退化到市级而不是整体失败', () async {
      final catalog = _TagCatalogDouble(<String>{
        '$kAdministrativeTagRoot/中国/浙江省/杭州市',
      });

      final resolved = await GeoTagRefResolver(
        catalog,
      ).resolveFromPoi(address: '浙江省杭州市西湖区北山街道1号');

      expect(resolved, '$kAdministrativeTagRoot/中国/浙江省/杭州市');
      expect(catalog.resolveCalls, hasLength(2));
    });

    test('全部候选都不存在时返回 null，不写入不存在的路径', () async {
      final catalog = _TagCatalogDouble(<String>{});

      final resolved = await GeoTagRefResolver(
        catalog,
      ).resolveFromPoi(address: '浙江省杭州市西湖区');

      expect(resolved, isNull);
    });

    test('候选数量受 maxCandidates 约束，不为可选字段打满往返', () async {
      final catalog = _TagCatalogDouble(<String>{});

      await GeoTagRefResolver(
        catalog,
        maxCandidates: 2,
      ).resolveFromPoi(address: '浙江省杭州市西湖区');

      expect(catalog.resolveCalls, hasLength(2));
    });

    test('境外 POI 命中境外行政区标签', () async {
      final catalog = _TagCatalogDouble(<String>{
        '$kAdministrativeTagRoot/日本/东京都/新宿区',
      });

      final resolved = await GeoTagRefResolver(
        catalog,
      ).resolveFromPoi(address: '日本东京都新宿区西新宿2-8-1');

      expect(resolved, '$kAdministrativeTagRoot/日本/东京都/新宿区');
    });

    test('地址缺失时回退到 POI 名，仍解析不出则返回 null', () async {
      final catalog = _TagCatalogDouble(<String>{
        '$kAdministrativeTagRoot/中国/浙江省/杭州市',
      });

      expect(
        await GeoTagRefResolver(catalog).resolveFromPoi(name: '浙江省杭州市某某咖啡'),
        '$kAdministrativeTagRoot/中国/浙江省/杭州市',
      );
      expect(await GeoTagRefResolver(catalog).resolveFromPoi(), isNull);
      expect(
        await GeoTagRefResolver(catalog).resolveFromPoi(name: '某某咖啡'),
        isNull,
      );
    });
  });
}
