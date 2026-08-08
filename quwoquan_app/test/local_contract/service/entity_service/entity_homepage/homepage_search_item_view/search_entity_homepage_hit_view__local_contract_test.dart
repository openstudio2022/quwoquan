// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart';

void main() {
  test('Homepage search projection keeps its canonical public read shape', () {
    const view = SearchEntityHomepageHitView(
      homepageId: 'homepage-west-lake',
      name: '西湖',
      subtitle: '杭州西湖',
      placeName: '西湖风景名胜区',
      address: '浙江省杭州市西湖区',
      followerCount: 12,
      contentCount: 7,
    );

    expect(view.homepageId, 'homepage-west-lake');
    expect(view.name, '西湖');
    expect(view.subtitle, '杭州西湖');
    expect(view.placeName, '西湖风景名胜区');
    expect(view.address, '浙江省杭州市西湖区');
    expect(view.followerCount, 12);
    expect(view.contentCount, 7);
  });

  test('Homepage search projection defaults absent counters to zero', () {
    const view = SearchEntityHomepageHitView(
      homepageId: 'homepage-minimal',
      name: '未命名主页',
    );

    expect(view.subtitle, isNull);
    expect(view.placeName, isNull);
    expect(view.address, isNull);
    expect(view.followerCount, 0);
    expect(view.contentCount, 0);
  });
}
