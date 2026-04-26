import 'dart:io';

import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:test/test.dart';

void main() {
  group('Learning loop and profile contracts', () {
    test('run request supports profile facets and multi-tone tags', () {
      const request = AssistantRunRequest(
        sessionId: 'profile-contract',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: 'test'),
        ],
        userProfileSnapshot: <String, dynamic>{
          'basicIdentity': <String, dynamic>{
            'age': 28,
            'gender': 'female',
            'birthdaySolar': '1998-08-08',
            'birthdayLunar': '农历七月初七',
          },
          'ipResidenceProfile': <String, dynamic>{
            'home': 'shenzhen_nanshan',
            'office': 'shenzhen_futian',
            'study': 'shenzhen_university_town',
          },
          'tonePreferences': <String, dynamic>{
            'communication_style_tags': <String>[
              'business_formal',
              'humorous',
              'respectful',
            ],
          },
        },
      );
      final roundTrip = AssistantRunRequest.fromJson(request.toJson());
      final snapshot = roundTrip.userProfileSnapshot;
      expect((snapshot['basicIdentity'] as Map?)?['birthdaySolar'], isNotNull);
      expect((snapshot['basicIdentity'] as Map?)?['birthdayLunar'], isNotNull);
      expect((snapshot['ipResidenceProfile'] as Map?)?['home'], isNotNull);
      final tags =
          (((snapshot['tonePreferences'] as Map?)?['communication_style_tags']
                  as List?)
              ?.whereType<String>()
              .toList(growable: false)) ??
          const <String>[];
      expect(tags.length >= 2, isTrue);
    });

    test(
      'agent consumes profile snapshot read-only and carries learning fields',
      () async {
        final tempDir = await Directory.systemTemp.createTemp('pa_learning_');
        final runtime = ReactRuntime(
          llmProvider: const HeuristicLocalLlmProvider(),
          toolRegistry: AssistantToolRegistry(),
        );
        final agentLoop = LocalPhaseExecutionOwner(
          runtime,
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final proposal = ProfileUpdateProposal(
          proposalId: 'proposal-1',
          profileVersionRead: 'v1.0',
          generatedAt: DateTime.now(),
          sourceRuns: const <String>['run-x'],
          confidence: 0.8,
          requiresUserConfirm: true,
          updates: const <ProfileUpdateItem>[
            ProfileUpdateItem(
              facet: 'interestTopics',
              path: 'interestTopics.tech',
              operation: 'add',
              newValue: 'ai_agent',
              oldValueSnapshot: <String>[],
              reason: '用户高频提问',
              evidenceRefs: <String>['msg#1'],
              itemConfidence: 0.8,
              riskLevel: 'low',
            ),
          ],
        );
        final request = AssistantRunRequest(
          sessionId: 'learning-contract',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '今天帮我规划学习计划'),
          ],
          userProfileSnapshot: const <String, dynamic>{
            'basicIdentity': <String, dynamic>{'age': 30, 'gender': 'male'},
          },
          contextScopeHint: <String, dynamic>{
            'profileUpdateProposal': proposal.toJson(),
          },
        );
        final response = await agentLoop.run(request);
        final structured = response.structuredResponse;
        expect(structured.containsKey('learningSignals'), isFalse);
        expect(structured.containsKey('basicIdentity'), isFalse);
        expect(
          response.profileUpdateProposal?.proposalId,
          equals('proposal-1'),
        );
        await tempDir.delete(recursive: true);
      },
    );
  });
}
