// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// readiness_case: persona_update_persona_app_api
// readiness_case: persona_retire_persona_app_api
// readiness_case: persona_activate_persona_app_api

/// Persona lifecycle production Remote API source contract.
///
/// This runner covers the generated-client command edge and lifecycle guards.
/// CreatePersona is setup only; the readiness cases cover the three lifecycle
/// operations whose guarded results are asserted by this runner.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() => harness.close());

  test(
    'create, update, activate, guard, and retire converge through production Remote',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final session = await harness.loginDisposableAccount('persona-$suffix');
      final primaryPersonaId =
          session.activePersona?.personaId ??
          (throw StateError('anonymous session has no active persona'));
      expect(primaryPersonaId, isNotEmpty);

      addTearDown(() async {
        await harness.accountLifecycle.closeAccount(
          CloseAccountCommand(
            clientRequestId: 'persona-api-cleanup-${session.ownerId}',
          ),
        );
      });

      final created = await harness.withIdempotencyKey(
        idempotencyKey: 'persona-create-$suffix',
        action: () => harness.personaCommands.createPersona(
          CreatePersonaCommand(
            displayName: 'Persona contract $suffix',
            isolationLevel: 'strict',
            purposeHint: 'api_contract',
          ),
        ),
      );
      final auxiliaryPersonaId = created.personaId;
      expect(auxiliaryPersonaId, isNotEmpty);
      expect(created.isPrimary, false);
      expect(created.isActive, false);
      expect(created.status, PersonaStatus.active);

      final updated = await harness.withIdempotencyKey(
        idempotencyKey: 'persona-update-$suffix',
        action: () => harness.personaCommands.updatePersona(
          UpdatePersonaCommand(
            personaId: auxiliaryPersonaId,
            displayName: 'Persona contract updated $suffix',
            purposeHint: 'api_contract_updated',
          ),
        ),
      );
      expect(updated.displayName, 'Persona contract updated $suffix');
      expect(updated.purposeHint, 'api_contract_updated');

      final activated = await harness.withIdempotencyKey(
        idempotencyKey: 'persona-activate-$suffix',
        action: () => harness.activatePersona(
          ActivatePersonaCommand(personaId: auxiliaryPersonaId),
        ),
      );
      expect(activated.personaId, auxiliaryPersonaId);
      expect(activated.isPrimary, false);

      await expectLater(
        harness.withIdempotencyKey(
          idempotencyKey: 'persona-primary-retire-$suffix',
          action: () => harness.personaCommands.retirePersona(
            RetirePersonaCommand(personaId: primaryPersonaId),
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.code,
            'code',
            UserErrorCode.primaryPersonaGuard.code,
          ),
        ),
      );

      final restored = await harness.withIdempotencyKey(
        idempotencyKey: 'persona-restore-primary-$suffix',
        action: () => harness.activatePersona(
          ActivatePersonaCommand(personaId: primaryPersonaId),
        ),
      );
      expect(restored.personaId, primaryPersonaId);
      expect(restored.isPrimary, true);

      final retired = await harness.withIdempotencyKey(
        idempotencyKey: 'persona-retire-$suffix',
        action: () => harness.personaCommands.retirePersona(
          RetirePersonaCommand(personaId: auxiliaryPersonaId),
        ),
      );
      expect(retired.personaId, auxiliaryPersonaId);
      expect(retired.allowed, true);
      expect(retired.reason, PersonaLifecycleGuardReason.allowed);

      await expectLater(
        harness.withIdempotencyKey(
          idempotencyKey: 'persona-retired-update-$suffix',
          action: () => harness.personaCommands.updatePersona(
            UpdatePersonaCommand(
              personaId: auxiliaryPersonaId,
              displayName: 'Retired persona must not update',
            ),
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.code,
            'code',
            UserErrorCode.retiredPersonaGuard.code,
          ),
        ),
      );
      await expectLater(
        harness.withIdempotencyKey(
          idempotencyKey: 'persona-retired-activate-$suffix',
          action: () => harness.activatePersona(
            ActivatePersonaCommand(personaId: auxiliaryPersonaId),
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.code,
            'code',
            UserErrorCode.retiredPersonaGuard.code,
          ),
        ),
      );
    },
  );
}
