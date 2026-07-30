import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CallStatus, CallType;

/// Golden：`test/support/fixtures/rtc/list_calls_min_response.json` 与 rtc ListCalls 分页形状一致。
void main() {
  test('ListCalls golden JSON → CallSessionDto', () {
    final path =
        '${Directory.current.path}/test/support/fixtures/rtc/list_calls_min_response.json';
    final raw =
        jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final obj = CloudResponseDecoder.asObject(raw, context: 'test.ListCalls');
    final items = obj['items'];
    expect(items, isA<List>());
    final first = (items! as List).single as Map<String, dynamic>;
    final dto = CallSessionDto.fromMap(first);
    expect(dto.callId, equals('call_golden_001'));
    expect(dto.callType, CallType.audio);
    expect(dto.status, CallStatus.ended);
    expect(dto.initiatorId, equals('user_golden'));
    expect(dto.roomId, equals('room_golden'));
  });
}
