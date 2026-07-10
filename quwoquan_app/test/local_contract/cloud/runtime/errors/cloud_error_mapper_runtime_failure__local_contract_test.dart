import 'dart:convert';
import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('CloudErrorMapper parses RuntimeErrorResponse', () {
    final body = jsonEncode(<String, dynamic>{
      'code': 'ASSISTANT.MIDDLEWARE.llm_timeout',
      'origin': 'remoteDependency',
      'kind': 'timeout',
      'nature': 'transient',
      'requestId': 'request-1',
      'traceId': 'trace-1',
      'location': <String, dynamic>{
        'businessObject': 'assistant_turn',
        'functionModule': 'llm_client',
      },
      'context': <String, dynamic>{
        'attributes': <Map<String, String>>[
          <String, String>{'key': 'statusCode', 'value': '504'},
        ],
      },
    });

    final failure = CloudErrorMapper.runtimeFailureFromStatusCode(
      504,
      body: body,
    );

    expect(failure.code, 'ASSISTANT.MIDDLEWARE.llm_timeout');
    expect(failure.kind, RuntimeFailureKind.timeout);
    expect(failure.context.attributes.single.value, '504');
  });

  test('CloudErrorMapper creates fallback RuntimeFailure from status code', () {
    final exception = CloudErrorMapper.fromStatusCode(
      503,
      requestPath: '/assistant/run',
    );

    expect(exception.runtimeFailure?.kind, RuntimeFailureKind.unavailable);
    expect(exception.runtimeFailure?.context.attributes.first.value, '503');
  });

  test('CloudErrorMapper 兼容简化错误体里的 userMessage', () {
    final exception = CloudErrorMapper.fromStatusCode(
      404,
      body: jsonEncode(<String, dynamic>{
        'code': 'CONTENT.USER.post_not_found',
        'userMessage': '内容不存在或已删除',
      }),
      requestPath: '/content/posts/deleted',
    );

    expect(exception.userMessage, '内容不存在或已删除');
    expect(exception.code, 'CONTENT.USER.post_not_found');
    expect(exception.runtimeFailure?.kind, RuntimeFailureKind.notFound);
  });

  test('CloudErrorMapper maps local runtime exceptions', () {
    final timeout = CloudErrorMapper.runtimeFailureFromException(
      TimeoutException('slow'),
      requestPath: '/assistant/run',
    );
    final offline = CloudErrorMapper.runtimeFailureFromException(
      const SocketException('offline'),
    );
    final invalidJson = CloudErrorMapper.runtimeFailureFromException(
      const FormatException('bad json'),
    );
    final permission = CloudErrorMapper.runtimeFailureFromException(
      PlatformException(code: 'permission_denied'),
    );

    expect(timeout.kind, RuntimeFailureKind.timeout);
    expect(offline.kind, RuntimeFailureKind.network);
    expect(invalidJson.kind, RuntimeFailureKind.parsing);
    expect(permission.nature, RuntimeFailureNature.requiresPermission);
  });

  test('CloudErrorMapper resolves typed DomainErrorCode for every generated client-visible domain', () {
    final cases = <String, String>{
      'CONTENT.USER.post_not_found': 'content',
      'USER.AUTH.otp_mismatch': 'user',
      'CHAT.USER.conversation_not_found': 'chat',
      'RTC.USER.call_not_found': 'rtc',
      'INTEGRATION.USER.location_unavailable': 'integration_location',
      'ASSISTANT.MIDDLEWARE.upstream_timeout': 'assistant',
      'CIRCLE.USER.not_found': 'circle',
      'ENTITY.USER.homepage_not_found': 'entity',
    };

    for (final entry in cases.entries) {
      final exception = CloudErrorMapper.fromStatusCode(
        entry.key.contains('MIDDLEWARE') ? 504 : 400,
        body: jsonEncode(<String, dynamic>{
          'code': entry.key,
          'origin': 'user',
          'kind': 'validation',
          'nature': 'permanent',
          'userMessage': 'server says ${entry.key}',
          'location': <String, dynamic>{
            'businessObject': 'contract_probe',
            'functionModule': 'mapper_test',
          },
          'context': <String, dynamic>{'attributes': <Map<String, String>>[]},
          'recovery': <String, dynamic>{
            'action': 'surface',
            'disruptionLevel': 'inlineCard',
          },
        }),
      );

      expect(exception.domainErrorCode?.domain, entry.value);
      expect(exception.domainErrorCode?.code, entry.key);
      expect(exception.userMessage, 'server says ${entry.key}');
    }
  });

  test(
    'forward-compat: 未知/新错误码仍下发 userMessage + recovery 兜底（端侧未升级亦可处理）',
    () {
      // 模拟云侧新增了一个客户端尚无 typed 枚举的错误码：端侧不认识该 code，
      // 但必须仍能展示云端下发的 userMessage，并消费结构化 recovery。
      final body = jsonEncode(<String, dynamic>{
        'code': 'NEWDOMAIN.USER.brand_new_unmapped_reason',
        'origin': 'user',
        'kind': 'rateLimited',
        'nature': 'requiresUserAction',
        'requestId': 'req-9',
        'traceId': 'trace-9',
        'userMessage': '本功能太热门啦，请 30 秒后再试',
        'location': <String, dynamic>{
          'businessObject': 'new_object',
          'functionModule': 'new_module',
        },
        'context': <String, dynamic>{
          'attributes': <Map<String, String>>[],
        },
        'recovery': <String, dynamic>{
          'action': 'retry',
          'afterSeconds': 30,
          'disruptionLevel': 'transientLocal',
        },
      });

      final exception = CloudErrorMapper.fromStatusCode(
        429,
        body: body,
        requestPath: '/new/op',
      );

      // 未升级端侧无该 code 的 typed enum，但兜底链路完整：
      expect(exception.userMessage, '本功能太热门啦，请 30 秒后再试');
      expect(exception.errorCode, isNull);
      expect(exception.domainErrorCode, isNull);
      expect(
        exception.runtimeFailure?.code,
        'NEWDOMAIN.USER.brand_new_unmapped_reason',
      );
      final recovery = exception.runtimeFailure?.recovery;
      expect(recovery?.isPresent, isTrue);
      expect(recovery?.action, 'retry');
      expect(recovery?.afterSeconds, 30);
    },
  );

  test('CloudResponseDecoder contract failures carry RuntimeFailure', () {
    final error = expectAsync0(() {
      CloudResponseDecoder.asObject(<String>['not', 'an', 'object']);
    });

    try {
      error();
    } on CloudException catch (exception) {
      expect(exception.runtimeFailure?.kind, RuntimeFailureKind.contract);
      expect(exception.runtimeFailure?.code, 'APP.CONTRACT.invalid_response');
      return;
    }
    fail('CloudResponseDecoder should throw CloudException');
  });
}
