import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_resolution_catalog.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('GeoResolutionCatalog 从配置表加载国家与时区映射', () async {
    final catalog = await GeoResolutionCatalog.load(forceRefresh: true);

    expect(
      catalog.resolveCountryCode(locale: 'zh_CN', timezone: ''),
      'CN',
    );
    expect(
      catalog.resolveCountryCode(locale: '', timezone: 'Asia/Hong_Kong'),
      'HK',
    );
    expect(catalog.countryLabelFor('US'), '美国');
  });
}
