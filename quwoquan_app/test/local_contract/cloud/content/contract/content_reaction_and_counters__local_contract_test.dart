import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('ContentReactionStateSlice.fromWire', () {
    test('parses liked and postId', () {
      final s = ContentReactionStateSlice.fromWire(<String, Object?>{
        'found': true,
        'postId': 'p1',
        'liked': true,
        'version': 3,
      });
      expect(s.postId, 'p1');
      expect(s.found, isTrue);
      expect(s.liked, isTrue);
      expect(s.version, 3);
    });

    test('rejects retired mixed reaction/share aliases', () {
      expect(
        () => ContentReactionStateSlice.fromWire(<String, Object?>{
          'found': true,
          'postId': 'p1',
          'liked': true,
          'version': 1,
          'shared': true,
        }),
        throwsFormatException,
      );
    });
  });
}
