import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:test/test.dart';

void main() {
  group('Protocol compatibility', () {
    test('run request supports json roundtrip', () {
      const request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: 'hello'),
          AssistantRunMessage(role: 'assistant', content: 'hi'),
        ],
        sessionId: 's1',
        userId: 'u1',
        deviceProfile: 'mobile',
        maxIterations: 3,
        userProfileSnapshot: <String, dynamic>{
          'profileVersion': 'v1',
          'basicIdentity': <String, dynamic>{'age': 28},
        },
      );

      final decoded = AssistantRunRequest.fromJson(request.toJson());
      expect(decoded.sessionId, equals('s1'));
      expect(decoded.userId, equals('u1'));
      expect(decoded.deviceProfile, equals('mobile'));
      expect(decoded.maxIterations, equals(3));
      expect(decoded.messages.length, equals(2));
      expect(decoded.userProfileSnapshot['profileVersion'], equals('v1'));
    });

    test('run request gateway body keeps extension keys', () {
      final req = AssistantRunRequest.fromGatewayBody(<String, dynamic>{
        'messages': <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': 'x'},
        ],
        'modelRef': 'm1',
        'customProbe': 42,
      });
      expect(req.messages, hasLength(1));
      expect(req.maxIterations, 8);
      expect(req.jsonExtension['modelRef'], 'm1');
      expect(req.jsonExtension['customProbe'], 42);
      final roundTrip = AssistantRunRequest.fromJson(req.toJson());
      expect(roundTrip.jsonExtension['modelRef'], 'm1');
      expect(roundTrip.jsonExtension['customProbe'], 42);
    });

    test('run response supports json roundtrip', () {
      final structuredPath =
          '../quwoquan_service/contracts/metadata/assistant/test_fixtures/wire_protocol_compatibility_structured_response.json';
      final structuredResponse = jsonDecode(File(structuredPath).readAsStringSync())
          as Map<String, dynamic>;
      final response = AssistantRunResponse(
        finalText: 'ok',
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'start',
            timestamp: DateTime.parse('2026-01-01T00:00:00Z'),
            data: const <String, dynamic>{'k': 'v'},
          ),
        ],
        degraded: true,
        errorCode: 'network_unavailable',
        structuredResponse: structuredResponse,
        profileUpdateProposal: ProfileUpdateProposal(
          proposalId: 'p_1',
          profileVersionRead: 'v1',
          generatedAt: DateTime.parse('2026-01-01T00:00:00Z'),
          sourceRuns: const <String>['run_1'],
          confidence: 0.8,
          requiresUserConfirm: true,
          updates: const <ProfileUpdateItem>[
            ProfileUpdateItem(
              facet: 'tonePreferences',
              path: 'tonePreferences.communication_style_tags',
              operation: 'merge',
              newValue: <String>['business_formal', 'respectful'],
              oldValueSnapshot: <String>['business_formal'],
              reason: 'user repeatedly prefers formal tone',
              evidenceRefs: <String>['trace_1'],
              itemConfidence: 0.75,
              riskLevel: 'low',
            ),
          ],
        ),
      );
      final decoded = AssistantRunResponse.fromJson(response.toJson());
      expect(decoded.finalText, equals('ok'));
      expect(decoded.degraded, isTrue);
      expect(decoded.errorCode, equals('network_unavailable'));
      expect(
        decoded.traces.first.type,
        equals(AssistantTraceEventType.lifecycleStart),
      );
      expect(decoded.traces.first.data?['k'], equals('v'));
      expect(decoded.structuredResponse['experimentBucket'], equals('control'));
      expect(
        (decoded.structuredResponse['uiTimeline'] as List?)?.isNotEmpty,
        isTrue,
      );
      expect(
        (decoded.structuredResponse['uiReferences'] as List?)?.isNotEmpty,
        isTrue,
      );
      expect(
        (decoded.structuredResponse['uiActions'] as List?)?.isNotEmpty,
        isTrue,
      );
      expect(decoded.profileUpdateProposal?.proposalId, equals('p_1'));
    });

    test('tool result supports unified fields', () {
      const result = AssistantToolResult(
        success: false,
        message: 'failed',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
      final decoded = AssistantToolResult.fromJson(result.toJson());
      expect(decoded.success, isFalse);
      expect(decoded.errorCode, equals(AssistantErrorCode.executionFailed));
      expect(decoded.degraded, isTrue);
    });
  });
}
