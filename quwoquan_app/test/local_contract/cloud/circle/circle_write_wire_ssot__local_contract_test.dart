import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_write_wire_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_write_wire_writable_keys.g.dart';

void main() {
  test('CreateCircle List/Set 与 service.yaml 成员一致', () {
    expect(
      CircleWriteWireWritableKeys.createCircleServiceFieldOrder.toSet(),
      CircleWriteWireWritableKeys.createCircle,
    );
    expect(
      CircleWriteWireWritableKeys.createCircleGroupServiceFieldOrder.toSet(),
      CircleWriteWireWritableKeys.createCircleGroup,
    );
  });

  test('CircleCreateWireDto.toRequestMap 覆盖 CreateCircle 全部可写字段', () {
    final dto = CircleCreateWireDto(
      name: 'n',
      description: 'd',
      coverUrl: 'c',
      category: 'cat',
      subCategory: 'sub',
      tags: const ['t'],
      visibility: 'public',
      joinPolicy: 'open',
      kind: 'interest',
      displaySubjectType: 'circle',
      followEnabled: true,
      linkedHomepageId: 'h1',
      linkedHomepageType: 'post',
      linkedHomepageTitle: 'ht',
    );
    final m = dto.toRequestMap();
    for (final k in CircleWriteWireWritableKeys.createCircle) {
      expect(m.containsKey(k), isTrue, reason: 'missing $k');
    }
  });
}
