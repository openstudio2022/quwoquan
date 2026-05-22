import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import 'rtc_test_fixtures.dart';

void main() {
  group('RemoteRtcRepository — wire 形状', () {
    test('ListCalls 接受 cursor 字段（rtc-service）', () async {
      final client = MockClient((request) async {
        expect(request.method, equals('GET'));
        if (request.url.path.endsWith('/v1/rtc/calls')) {
          return http.Response(
            rtcListCallsResponseJsonWithCursor(),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });

      final repo = RemoteRtcRepository(
        httpClient: CloudHttpClient(client: client),
      );
      final list = await repo.listCallHistory(limit: 10);
      expect(list, hasLength(1));
      expect(list.single.id, equals('call_x'));
    });

    test(
      'initiateCall 请求体与 RtcInitiateCallRequestWire 一致（省略 null 可选字段）',
      () async {
        http.BaseRequest? captured;
        final client = MockClient((request) async {
          captured = request;
          return http.Response(
            '{"token":"t","session":{"_id":"c0","callType":"audio","status":"ringing","initiatorId":"u0","roomId":"r0","maxParticipants":8,"participantCount":1,"createdAt":"2026-01-01T00:00:00Z","updatedAt":"2026-01-01T00:00:00Z"}}',
            200,
            headers: {'content-type': 'application/json'},
          );
        });

        final repo = RemoteRtcRepository(
          httpClient: CloudHttpClient(client: client),
        );
        await repo.initiateCall(
          callType: 'audio',
          inviteeIds: const ['u1'],
          maxParticipants: 8,
        );

        expect(captured, isNotNull);
        final body = utf8.decode((captured as http.Request).bodyBytes);
        final json = jsonDecode(body) as Map<String, dynamic>;
        expect(json['callType'], equals('audio'));
        expect(json['inviteeIds'], equals(['u1']));
        expect(json['maxParticipants'], equals(8));
        expect(json.containsKey('conversationId'), isFalse);
        expect(json.containsKey('circleId'), isFalse);
      },
    );

    test('ListCalls 缺少 items 时抛出携带 RuntimeFailure 的 CloudException', () async {
      final client = MockClient((request) async {
        return http.Response('{"unexpected":[]}', 200);
      });

      final repo = RemoteRtcRepository(
        httpClient: CloudHttpClient(client: client),
      );

      await expectLater(
        repo.listCallHistory(),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.runtimeFailure?.code,
                'runtimeFailure.code',
                'APP.CONTRACT.invalid_response',
              )
              .having(
                (error) => error.runtimeFailure?.kind,
                'runtimeFailure.kind',
                RuntimeFailureKind.contract,
              ),
        ),
      );
    });

    test('inviteToCall 请求体使用 inviteeIds', () async {
      http.BaseRequest? captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response('{}', 200);
      });

      final repo = RemoteRtcRepository(
        httpClient: CloudHttpClient(client: client),
      );
      await repo.inviteToCall(callId: 'c1', inviteeIds: ['u9']);

      expect(captured, isNotNull);
      expect(captured!.method, equals('POST'));
      final body = utf8.decode((captured as http.Request).bodyBytes);
      final json = jsonDecode(body) as Map<String, dynamic>;
      expect(json['inviteeIds'], equals(['u9']));
      expect(json.containsKey('userIds'), isFalse);
    });

    test('cameraToggle 使用 POST 与 cameraOn', () async {
      http.BaseRequest? captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response('{}', 200);
      });

      final repo = RemoteRtcRepository(
        httpClient: CloudHttpClient(client: client),
      );
      await repo.cameraToggle(callId: 'c1', cameraOn: true);

      expect(captured!.method, equals('POST'));
      final body = utf8.decode((captured as http.Request).bodyBytes);
      expect(jsonDecode(body), equals({'cameraOn': true}));
    });
  });
}
