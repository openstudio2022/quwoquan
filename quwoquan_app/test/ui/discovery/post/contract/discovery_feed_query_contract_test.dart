import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

void main() {
  group('DiscoveryFeedQuery contract', () {
    test('moment rail maps to identity=moment without type', () {
      final query = toDiscoveryFeedQuery('moment');
      expect(query.identity, 'moment');
      expect(query.type, isNull);
    });

    test('work format tabs map to identity=work with typed filters', () {
      expect(toDiscoveryFeedQuery('photo').type, 'image');
      expect(toDiscoveryFeedQuery('video').type, 'video');
      expect(toDiscoveryFeedQuery('article').type, 'article');
      expect(toDiscoveryFeedQuery('photo').identity, 'work');
    });
  });
}
