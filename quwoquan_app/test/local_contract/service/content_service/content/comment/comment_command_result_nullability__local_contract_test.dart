// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('CommentCommandResult generated decoder nullability', () {
    test('preserves an explicit false replayed value', () {
      final result = decodeCommentCommandResult(<String, Object?>{
        'id': 'comment-1',
        'version': 1,
        'status': 'active',
        'replayed': false,
      });

      expect(result.replayed, isFalse);
      expect(result.toWire()['replayed'], isFalse);
    });

    test('rejects a missing replayed key instead of defaulting to false', () {
      expect(
        () => decodeCommentCommandResult(<String, Object?>{
          'id': 'comment-1',
          'version': 1,
          'status': 'active',
        }),
        throwsFormatException,
      );
    });
  });
}
