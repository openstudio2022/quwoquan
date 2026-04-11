import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';

/// Golden：`test/cloud/rtc/fixtures/list_calls_min_response.json` 与 rtc ListCalls 分页形状一致。
void main() {
  test('ListCalls golden JSON → CallSessionDto', () {
    final path = '${Directory.current.path}/test/cloud/rtc/fixtures/list_calls_min_response.json';
    final raw = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final obj = CloudResponseDecoder.asObject(raw, context: 'test.ListCalls');
    final items = obj['items'];
    expect(items, isA<List>());
    final first = (items! as List).single as Map<String, dynamic>;
    final dto = CallSessionDto.fromMap(first);
    expect(dto.id, equals('call_golden_001'));
    expect(dto.callType, equals('audio'));
    expect(dto.status, equals('ended'));
    expect(dto.initiatorId, equals('user_golden'));
    expect(dto.roomId, equals('room_golden'));
  });
}
