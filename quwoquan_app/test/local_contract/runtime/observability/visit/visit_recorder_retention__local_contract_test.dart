// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';

void main() {
  test(
    'visit experience hints retain only the most recent bounded LRU set',
    () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'visit_recorder_retention_test_',
      );
      Hive.init(tempDir.path);
      const boxName = 'visit_recorder_retention';
      final box = await Hive.openBox<String>(boxName);
      final base = DateTime.utc(2026, 1, 1);
      final seeded = <String, String>{};
      for (var index = 0; index < kVisitRecordRetentionLimit; index += 1) {
        final targetKey = 'page_retained_$index';
        final seenAt = base.add(Duration(minutes: index));
        seeded[targetKey] = jsonEncode(
          VisitRecord(
            targetKey: targetKey,
            firstSeenAt: seenAt,
            lastSeenAt: seenAt,
            visitCount: 1,
            count7d: 1,
            count30d: 1,
            lastSeenTimestamps: <String>[seenAt.toIso8601String()],
          ).toStorageMap(),
        );
      }
      await box.putAll(seeded);
      final service = VisitRecorderService(boxName: boxName);

      await service.recordVisit(const VisitTarget.page('newest'));

      expect(box.length, kVisitRecordRetentionLimit);
      expect(box.containsKey('page_retained_0'), isFalse);
      expect(box.containsKey('page_retained_1'), isTrue);
      expect(box.containsKey('page_newest'), isTrue);
      expect(
        service.getExperience(const VisitTarget.page('retained_0')),
        ExperienceLevel.firstTime,
      );

      await Hive.deleteFromDisk();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    },
  );
}
