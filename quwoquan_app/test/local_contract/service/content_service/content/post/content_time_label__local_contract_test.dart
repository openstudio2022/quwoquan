import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_time_label.dart';

void main() {
  group('ContentTimeLabel — 创作/更新时间展示规则 (T1)', () {
    test('未更新（updatedAt 为 null）：卡片只显示创作相对时间，无「已编辑」', () {
      final created = DateTime.now().subtract(const Duration(days: 3));
      final label = ContentTimeLabel.cardLabel(createdAt: created);
      expect(label.contains(ProfileText.contentEditedSuffix), isFalse);
    });

    test('更新时间不晚于创作时间（相等）：视为未更新', () {
      final t = DateTime(2026, 1, 1, 8);
      final label = ContentTimeLabel.cardLabel(createdAt: t, updatedAt: t);
      expect(label.contains(ProfileText.contentEditedSuffix), isFalse);
    });

    test('更新晚于创作超过 1 秒：卡片追加「已编辑」', () {
      final created = DateTime.now().subtract(const Duration(days: 3));
      final updated = created.add(const Duration(hours: 5));
      final label = ContentTimeLabel.cardLabel(
        createdAt: created,
        updatedAt: updated,
      );
      expect(label.contains(ProfileText.contentEditedSuffix), isTrue);
    });

    test('秒级抖动（<=1s）不算更新，避免幂等导入误报', () {
      final created = DateTime(2026, 1, 1, 8, 0, 0);
      final jitter = created.add(const Duration(milliseconds: 800));
      final label = ContentTimeLabel.cardLabel(
        createdAt: created,
        updatedAt: jitter,
      );
      expect(label.contains(ProfileText.contentEditedSuffix), isFalse);
    });

    test('阅读器时间行：未更新只展示「创作于 X」', () {
      final created = DateTime(2025, 5, 15);
      final line = ContentTimeLabel.readerLine(createdAt: created);
      expect(line.startsWith(ProfileText.contentCreatedAtPrefix), isTrue);
      expect(line.contains(ProfileText.contentUpdatedAtPrefix), isFalse);
      // 跨年补 yyyy年。
      expect(line.contains('2025年'), isTrue);
    });

    test('阅读器时间行：已更新展示「创作于 X · 更新于 Y」', () {
      final created = DateTime(2025, 5, 15);
      final updated = DateTime(2025, 6, 20);
      final line = ContentTimeLabel.readerLine(
        createdAt: created,
        updatedAt: updated,
      );
      expect(line.contains(ProfileText.contentCreatedAtPrefix), isTrue);
      expect(line.contains(ProfileText.contentUpdatedAtPrefix), isTrue);
    });
  });
}
