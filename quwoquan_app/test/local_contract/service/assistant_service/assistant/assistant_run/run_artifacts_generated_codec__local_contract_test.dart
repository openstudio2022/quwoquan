import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/run_artifacts.dart';

void main() {
  test(
    'generated run artifacts codec covers nested answer and diagnostics data',
    () {
      final core = RunArtifactsAnswerDecisionCore.fromJson(<String, dynamic>{
        'nextAction': ' answer ',
        'answerEligibility': ' eligible ',
        'finalAnswerReady': true,
        'evidenceSummary': ' enough ',
        'confidence': 0.8,
        'reasoning': ' checked ',
        'synthesisReady': true,
        'synthesisReason': ' complete ',
      });
      final processing = RunArtifactsAnswerProcessing.fromJson(
        <String, dynamic>{
          'readinessSummary': ' ready ',
          'keyFacts': <String>[' one ', ''],
          'missingDimensions': <String>[' two '],
          'retrieveMoreReason': ' none ',
        },
      );
      final displayItem = AssistantDisplayItem.fromJson(<String, dynamic>{
        'itemId': ' item-1 ',
        'title': ' title ',
        'body': ' body ',
        'referenceIds': <String>[' ref-1 ', ''],
      });
      final policy = DomainPolicyBundle.fromJson(<String, dynamic>{
        'domainId': ' assistant ',
        'executionPolicy': <String, dynamic>{'mode': 'guided'},
        'slotSchema': <String, dynamic>{'required': true},
        'dialoguePolicy': <String, dynamic>{'turns': 3},
        'authorityPolicy': <String, dynamic>{'level': 'primary'},
        'retrievalPolicy': <String, dynamic>{'fresh': true},
        'answerPolicy': <String, dynamic>{'citations': true},
        'narrativePolicy': <String, dynamic>{'concise': true},
      });
      final slot = SlotValueSnapshot.fromJson(<String, dynamic>{
        'slotId': ' destination ',
        'status': 'inferred',
        'value': <String, dynamic>{'city': 'Hangzhou'},
        'source': ' profile ',
        'confidence': 0.9,
        'updatedAt': ' 2030-01-01T00:00:00Z ',
        'note': ' inferred ',
        'candidates': <String>[' Hangzhou ', ''],
        'evidenceIds': <String>[' ev-1 ', ''],
      });
      final resolution = RunArtifactsUnderstandingResolutionItem.fromJson(
        <String, dynamic>{
          'kind': 'fact',
          'title': ' destination ',
          'detail': ' resolved ',
          'source': ' profile ',
          'originalValue': ' home ',
          'resolvedValue': ' Hangzhou ',
          'defaultApplied': true,
          'visibleInUnderstanding': false,
        },
      );
      final diagnostics = RunArtifactsDiagnosticsCore.fromJson(
        <String, dynamic>{
          'domainId': ' assistant ',
          'renderMode': ' markdown ',
          'renderFallback': ' plain_text ',
          'answerEligibility': ' eligible ',
          'qualityGates': <String, dynamic>{'passed': true},
          'evidenceEvaluation': <String, dynamic>{'score': 1},
          'answerBoundaryPolicy': <String, dynamic>{'safe': true},
          'evidenceSummary': ' enough ',
          'evidencePassed': true,
          'finalAnswerMode': ' answer ',
          'synthesisReady': true,
          'synthesisReason': ' complete ',
          'heuristicFallbackUsed': false,
          'emergedTags': <String>[' grounded ', ''],
        },
      );

      expect(core.nextAction, 'answer');
      expect(core.confidence, 0.8);
      expect(core.toJson()['finalAnswerReady'], isTrue);
      expect(processing.keyFacts, <String>['one']);
      expect(processing.toJson()['missingDimensions'], <String>['two']);
      expect(diagnostics.domainId, 'assistant');
      expect(diagnostics.qualityGates['passed'], isTrue);
      expect(diagnostics.emergedTags, <String>['grounded']);
      expect(diagnostics.toJson()['evidencePassed'], isTrue);
      expect(displayItem.itemId, 'item-1');
      expect(displayItem.referenceIds, <String>['ref-1']);
      expect(displayItem.toJson()['title'], 'title');
      expect(policy.executionPolicy['mode'], 'guided');
      expect(policy.toJson()['domainId'], 'assistant');
      expect(slot.slotId, 'destination');
      expect(slot.candidates, <String>['Hangzhou']);
      expect(slot.toJson()['confidence'], 0.9);
      expect(resolution.resolvedValue, 'Hangzhou');
      expect(resolution.visibleInUnderstanding, isFalse);
      expect(resolution.toJson()['defaultApplied'], isTrue);
    },
  );

  test(
    'generated run artifacts codec rejects unknown and invalid wire values',
    () {
      expect(
        () => RunArtifactsAnswerDecisionCore.fromJson(<String, dynamic>{
          'unknown': true,
        }),
        throwsFormatException,
      );
      expect(
        () => RunArtifactsAnswerDecisionCore.fromJson(<String, dynamic>{
          'confidence': 'high',
        }),
        throwsFormatException,
      );
      expect(
        () => RunArtifactsAnswerProcessing.fromJson(<String, dynamic>{
          'keyFacts': <Object>[1],
        }),
        throwsFormatException,
      );
      expect(
        () => RunArtifactsDiagnosticsCore.fromJson(<String, dynamic>{
          'qualityGates': <Object>[],
        }),
        throwsFormatException,
      );
      expect(
        () => RunArtifactsDiagnosticsCore.fromJson(<String, dynamic>{
          'emergedTags': <Object>[1],
        }),
        throwsFormatException,
      );
      expect(
        () => AssistantDisplayItem.fromJson(<String, dynamic>{'title': 1}),
        throwsFormatException,
      );
      expect(
        () => DomainPolicyBundle.fromJson(<String, dynamic>{
          'answerPolicy': <Object>[],
        }),
        throwsFormatException,
      );
      expect(
        () => SlotValueSnapshot.fromJson(<String, dynamic>{
          'slotId': 'destination',
          'candidates': <Object>[1],
        }),
        throwsFormatException,
      );
      expect(
        () => RunArtifactsUnderstandingResolutionItem.fromJson(
          <String, dynamic>{'defaultApplied': 'yes'},
        ),
        throwsFormatException,
      );
    },
  );
}
