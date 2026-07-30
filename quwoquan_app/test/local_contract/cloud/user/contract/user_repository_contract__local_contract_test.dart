import 'package:test/test.dart';
import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import '../../../../support/cloud_services/mock_persona_facets.dart';

void main() {
  group('Persona Query/Command Facet — 常规契约', () {
    late PersonaQuery query;
    late MockPersonaFacets commandWriter;

    setUp(() {
      commandWriter = MockPersonaFacets();
      query = commandWriter;
    });

    test('listPersonas 返回分身列表', () async {
      final accounts = await query.listPersonas();
      expect(accounts, isNotEmpty);
      expect(accounts.first.personaId, isNotEmpty);
    });

    test('getPersonaManagementSummary 返回 quota 与 items', () async {
      final summary = await query.getPersonaManagementSummary();
      expect(summary.items, isNotEmpty);
      expect(summary.quota.maxPersonas, greaterThan(0));
    });

    test(
      'getPersonaManagementSummary 与 activeContext 显式暴露 avatarVersion',
      () async {
        final summary = await query.getPersonaManagementSummary();
        expect(summary.items, isNotEmpty);
        final primary = summary.items.first;
        // avatarUrl 经 MediaDeliveryResolver 解析；flutter test 无
        // dart-define CDN endpoint 时解析为空串，此处只断言版本语义。
        expect(primary.avatarVersion, greaterThanOrEqualTo(0));
        expect(summary.activeContext, isNotNull);
        expect(summary.activeContext!.avatarVersion, greaterThanOrEqualTo(0));
      },
    );

    test('getActivePersonaContext 返回活动身份上下文', () async {
      final context = await query.getActivePersonaContext();
      expect(context.personaId, isNotEmpty);
    });

    test('getActivePersonaContext 与 Query 当前分身对齐', () async {
      final context = await query.getActivePersonaContext();
      expect(context.personaId, 'persona_primary');
      expect(context.ownerUserId, 'owner-test');
      expect(context.displayName, isNotEmpty);
    });

    test('activatePersona 切换到已存在分身', () async {
      final personas = await query.listPersonas();
      final target = personas.last.personaId;
      await expectLater(
        commandWriter.activatePersona(
          contracts.ActivatePersonaCommand(personaId: target),
        ),
        completes,
      );
    });

    test('applyPersonaProfileSync 返回已应用数量', () async {
      final result = await commandWriter.applyPersonaProfileSync(
        contracts.ApplyPersonaProfileSyncCommand(
          personaId: 'persona_primary',
          applyScope: 'all_personas',
          fieldsMask: const <String>['phone', 'email'],
        ),
      );
      expect(result.appliedCount, greaterThanOrEqualTo(0));
    });
  });

  group('Persona Query/Command Facet — 异常/边界契约', () {
    test('activatePersona 空 ID fail-fast', () {
      expect(
        () => contracts.ActivatePersonaCommand(personaId: ''),
        throwsArgumentError,
      );
    });

    test('retirePersona 空 ID fail-fast', () {
      expect(
        () => contracts.RetirePersonaCommand(personaId: ''),
        throwsArgumentError,
      );
    });
  });
}
