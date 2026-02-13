import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:test/test.dart';

void main() {
  group('ImageEditorFilterRepository recent presets', () {
    test('deduplicates and keeps latest usage first', () async {
      final result = ImageEditorFilterRepository.mergeRecentPresetIds(
        const <String>['preset_b', 'preset_a'],
        'preset_a',
      );
      expect(result, equals(<String>['preset_a', 'preset_b']));
    });

    test('truncates list with max count limit', () async {
      var state = <String>[];
      for (var i = 0; i < 20; i++) {
        state = ImageEditorFilterRepository.mergeRecentPresetIds(
          state,
          'preset_$i',
        );
      }
      expect(state.length, lessThanOrEqualTo(8));
      expect(state.first, equals('preset_19'));
    });
  });
}
