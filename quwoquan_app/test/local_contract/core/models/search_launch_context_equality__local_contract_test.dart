import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

void main() {
  group('SearchObjectSelection', () {
    test('值相等与 Set 实例无关，hashCode 一致', () {
      const a = SearchObjectSelection(
        targets: {SearchObjectTarget.contacts},
        contentTypes: {SearchContentTypeFilter.article},
      );
      final b = SearchObjectSelection(
        targets: {SearchObjectTarget.contacts},
        contentTypes: {SearchContentTypeFilter.article},
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });

    test('枚举集合顺序不同仍相等', () {
      final a = SearchObjectSelection(
        contentTypes: {
          SearchContentTypeFilter.video,
          SearchContentTypeFilter.article,
        },
      );
      final b = SearchObjectSelection(
        contentTypes: {
          SearchContentTypeFilter.article,
          SearchContentTypeFilter.video,
        },
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });
  });

  group('SearchLaunchContext', () {
    test('字段相同则新建实例仍相等且 hash 一致', () {
      final a = SearchLaunchContext(
        entrySurfaceId: 'surface',
        prefilledQuery: 'hello',
        searchObjectSelection: const SearchObjectSelection(
          targets: {SearchObjectTarget.circles},
        ),
      );
      final b = SearchLaunchContext(
        entrySurfaceId: 'surface',
        prefilledQuery: 'hello',
        searchObjectSelection: SearchObjectSelection(
          targets: {SearchObjectTarget.circles},
        ),
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });

    test('prefilledQuery 不同则不等', () {
      final a = SearchLaunchContext(entrySurfaceId: 'x');
      final b = SearchLaunchContext(entrySurfaceId: 'x', prefilledQuery: 'y');
      expect(a, isNot(equals(b)));
    });
  });
}
