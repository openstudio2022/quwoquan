import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/rtc_contracts.dart'
    show CallSession, CallStatus, CallType;

/// Golden：`test/support/fixtures/rtc/list_calls_min_response.json` 与 rtc ListCalls 分页形状一致。
void main() {
  test('ListCalls golden JSON → CallSession', () {
    final path =
        '${Directory.current.path}/test/support/fixtures/rtc/list_calls_min_response.json';
    final raw =
        jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final items = raw['items'];
    expect(items, isA<List>());
    final first = (items! as List).single as Map<String, dynamic>;
    final dto = CallSession.fromWire(first);
    expect(dto.id, equals('call_golden_001'));
    expect(dto.callType, CallType.audio);
    expect(dto.status, CallStatus.ended);
    expect(dto.initiatorId, equals('user_golden'));
    expect(dto.roomId, equals('room_golden'));
  });
}
