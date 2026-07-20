import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_write_wire_writable_keys.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('CreateCircle List/Set 与 service.yaml 成员一致', () {
    expect(
      CircleWriteWireWritableKeys.createCircleServiceFieldOrder.toSet(),
      CircleWriteWireWritableKeys.createCircle,
    );
  });

  test('CreateCircle typed encoder 覆盖 metadata 全部可写字段', () {
    final command = CreateCircleCommand(
      name: 'n',
      description: 'd',
      rulesText: 'r',
      welcomeMessage: 'w',
      coverUrl: 'c',
      iconUrl: 'i',
      category: 'cat',
      subCategory: 'sub',
      tags: const ['t'],
      visibility: 'public',
      joinPolicy: 'open',
      kind: 'interest',
      displaySubjectType: 'circle',
      followEnabled: true,
      autoSyncChat: true,
      linkedHomepageId: 'h1',
      linkedHomepageType: 'post',
      linkedHomepageTitle: 'ht',
    );
    final m = encodeCreateCircleCommand(command).body;
    for (final k in CircleWriteWireWritableKeys.createCircle) {
      expect(m.containsKey(k), isTrue, reason: 'missing $k');
    }
  });
}
