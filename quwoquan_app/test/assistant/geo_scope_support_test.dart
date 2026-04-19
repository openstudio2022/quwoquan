import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:test/test.dart';

void main() {
  group('geo_scope_support', () {
    test('structured current geo scope is preserved', () {
      final scope = resolveGeoScope(
        current: const ResolvedGeoScope(
          geoKind: 'city',
          cityLabel: '北京',
          resolvedText: '北京',
          source: 'model_output',
          reason: 'structured_geo_scope',
        ),
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
      expect(scope.source, 'model_output');
      expect(scope.reason, 'structured_geo_scope');
    });

    test('previous structured geo scope is carried forward', () {
      final scope = resolveGeoScope(
        previous: const ResolvedGeoScope(
          geoKind: 'city',
          cityLabel: '深圳',
          resolvedText: '深圳',
          source: 'model_output',
          reason: 'structured_geo_scope',
        ),
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
      expect(scope.source, 'followup_carried');
      expect(scope.reason, 'structured_geo_scope');
    });

    test('finance 会按国家默认市场', () {
      final scope = resolveGeoScope(
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

    test('structured market override is preserved', () {
      final scope = resolveGeoScope(
        availableGeoContext: const AvailableGeoContext(
          countryCode: 'CN',
          countryLabel: '中国',
        ),
        geoPolicy: const DefaultGeoPolicy(
          defaultGeoScope: 'market',
          fallbackAllowed: true,
          marketOverrides: <String, String>{'CN': '中国股市/A股'},
        ),
      );

      expect(scope.geoKind, 'market');
      expect(scope.countryCode, 'CN');
      expect(scope.marketLabel, '中国股市/A股');
      expect(scope.resolvedText, '中国股市/A股');
      expect(scope.defaultApplied, isTrue);
    });
  });
}
