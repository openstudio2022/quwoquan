import 'package:quwoquan_app/assistant/api/assistant_gateway_json_payloads.dart';
import 'package:quwoquan_app/assistant/observability/assistant_observability_runtime.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantGatewayModelSelectBody', () {
    test('parses selectedModels and modelRef', () {
      final b = AssistantGatewayModelSelectBody.fromJson(<String, dynamic>{
        'selectedModels': <dynamic>['  a ', '', 'b'],
        'modelRef': ' m1 ',
      });
      expect(b.selectedModels, <String>['a', 'b']);
      expect(b.modelRef, 'm1');
    });
  });

  group('AssistantGatewayLogsExportBody', () {
    test('uses default directory when empty', () {
      final b = AssistantGatewayLogsExportBody.fromJson(<String, dynamic>{});
      expect(
        b.targetDirectory,
        AssistantGatewayLogsExportBody.kDefaultTargetDirectory,
      );
    });

    test('trims non-empty targetDirectory', () {
      final b = AssistantGatewayLogsExportBody.fromJson(<String, dynamic>{
        'targetDirectory': ' /tmp/logs ',
      });
      expect(b.targetDirectory, '/tmp/logs');
    });
  });

  group('AssistantGatewayLogsBoostBody', () {
    test('parses clear and ids', () {
      final b = AssistantGatewayLogsBoostBody.fromJson(<String, dynamic>{
        'sessionId': ' s1 ',
        'runId': ' r1 ',
        'clear': true,
      });
      expect(b.sessionId, 's1');
      expect(b.runId, 'r1');
      expect(b.clear, isTrue);
    });
  });

  group('AssistantGatewayAlertsTestBody', () {
    test('defaults match synthetic alert contract', () {
      final b = AssistantGatewayAlertsTestBody.fromJson(<String, dynamic>{});
      expect(b.severity, AssistantSloAlertSeverity.warning);
      expect(b.providerId, 'synthetic_provider');
      expect(b.message, contains('synthetic'));
    });

    test('critical severity', () {
      final b = AssistantGatewayAlertsTestBody.fromJson(<String, dynamic>{
        'severity': 'CRITICAL',
        'providerId': 'p1',
        'message': 'msg',
      });
      expect(b.severity, AssistantSloAlertSeverity.critical);
      expect(b.providerId, 'p1');
      expect(b.message, 'msg');
    });
  });

  group('AssistantGatewaySkillInvokeBody', () {
    test('parses snake_case skill id and arguments', () {
      final b = AssistantGatewaySkillInvokeBody.fromJson(<String, dynamic>{
        'skill_id': ' sk ',
        'userId': ' u1 ',
        'channel': ' c1 ',
        'arguments': <String, dynamic>{'x': 1},
        'deviceProfile': ' tablet ',
        'traceId': ' t1 ',
      });
      expect(b.skillId, 'sk');
      expect(b.actorUserId, 'u1');
      expect(b.channel, 'c1');
      expect(b.arguments, <String, dynamic>{'x': 1});
      expect(b.deviceProfile, 'tablet');
      expect(b.traceId, 't1');
    });
  });

  group('AssistantGatewayRunModelHintsBody', () {
    test('parses model hints', () {
      final b = AssistantGatewayRunModelHintsBody.fromJson(<String, dynamic>{
        'modelRef': ' ref ',
        'selectedModels': <dynamic>[' a ', 'b'],
      });
      expect(b.modelRef, 'ref');
      expect(b.selectedModels, <String>['a', 'b']);
    });
  });
}
