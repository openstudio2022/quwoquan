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
