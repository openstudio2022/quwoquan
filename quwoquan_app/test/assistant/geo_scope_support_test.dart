import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:test/test.dart';

void main() {
  group('geo_scope_support', () {
    test('weather 会优先使用显式城市', () {
      final scope = resolveGeoScope(
        userQuery: '北京明天天气怎么样',
        domainId: 'weather',
        availableGeoContext: const AvailableGeoContext(
          countryCode: 'CN',
          countryLabel: '中国',
          cityLabel: '深圳',
        ),
        geoPolicy: const DefaultGeoPolicy(
          defaultGeoScope: 'city',
          fallbackAllowed: true,
          fallbackSources: <String>['available_geo.city'],
        ),
      );

      expect(scope.geoKind, 'city');
      expect(scope.cityLabel, '北京');
      expect(scope.resolvedText, '北京');
      expect(scope.source, 'user_explicit');
      expect(scope.defaultApplied, isFalse);
    });

    test('weather 在缺少显式地点时会回落到设备城市', () {
      final scope = resolveGeoScope(
        userQuery: '明天天气怎么样',
        domainId: 'weather',
        availableGeoContext: const AvailableGeoContext(
          countryCode: 'CN',
          countryLabel: '中国',
          regionLabel: '广东',
          cityLabel: '深圳',
        ),
        geoPolicy: const DefaultGeoPolicy(
          defaultGeoScope: 'city',
          fallbackAllowed: true,
          fallbackSources: <String>[
            'available_geo.city',
            'available_geo.region',
          ],
        ),
      );

      expect(scope.geoKind, 'city');
      expect(scope.cityLabel, '深圳');
      expect(scope.resolvedText, '深圳');
      expect(scope.defaultApplied, isTrue);
      expect(scope.reason, 'weather_without_city_use_device_city');
    });

    test('finance 会按国家默认市场', () {
      final scope = resolveGeoScope(
        userQuery: '最近股市怎么样',
        domainId: 'finance_consumer',
        availableGeoContext: const AvailableGeoContext(
          countryCode: 'CN',
          countryLabel: '中国',
          cityLabel: '深圳',
        ),
        geoPolicy: const DefaultGeoPolicy(
          defaultGeoScope: 'market',
          fallbackAllowed: true,
          fallbackSources: <String>['available_geo.country'],
          marketOverrides: <String, String>{'CN': '中国股市/A股'},
        ),
      );

      expect(scope.geoKind, 'market');
      expect(scope.countryCode, 'CN');
      expect(scope.marketLabel, '中国股市/A股');
      expect(scope.resolvedText, '中国股市/A股');
      expect(scope.defaultApplied, isTrue);
    });

    test('finance 的显式市场 alias 来自配置而不是代码硬编码', () {
      final scope = resolveGeoScope(
        userQuery: '昨天A股为什么大涨',
        domainId: 'finance_consumer',
        availableGeoContext: const AvailableGeoContext(
          countryCode: 'CN',
          countryLabel: '中国',
        ),
        geoPolicy: const DefaultGeoPolicy(
          defaultGeoScope: 'market',
          fallbackAllowed: true,
          scopeCatalog: <GeoScopeCatalogEntry>[
            GeoScopeCatalogEntry(
              geoKind: 'market',
              countryCode: 'CN',
              countryLabel: '中国',
              marketCode: 'CN_A',
              marketLabel: '中国股市/A股',
              resolvedText: '中国股市/A股',
              aliases: <String>['A股', '沪深股市'],
              reason: 'user_explicit_market',
            ),
          ],
        ),
      );

      expect(scope.geoKind, 'market');
      expect(scope.marketCode, 'CN_A');
      expect(scope.marketLabel, '中国股市/A股');
      expect(scope.source, 'user_explicit');
      expect(scope.defaultApplied, isFalse);
    });

    test('applyResolvedGeoToQuery 会把 geography 写回检索词', () {
      const scope = ResolvedGeoScope(
        geoKind: 'city',
        cityLabel: '深圳',
        resolvedText: '深圳',
      );

      expect(
        applyResolvedGeoToQuery('明天 天气 预报', scope),
        '深圳 明天 天气 预报',
      );
      expect(
        applyResolvedGeoToQuery('2026-04-10 天气 预报', scope),
        '2026-04-10 深圳 天气 预报',
      );
      expect(
        applyResolvedGeoToQuery('深圳 明天 天气 预报', scope),
        '深圳 明天 天气 预报',
      );
    });
  });
}
