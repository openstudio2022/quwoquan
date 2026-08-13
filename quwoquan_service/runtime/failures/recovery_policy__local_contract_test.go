package failures

import "testing"

func TestDefaultRecoveryPolicyRetriesTransientFailureWithBudget(t *testing.T) {
	decision := DefaultRecoveryPolicy{}.Decide(
		Failure{
			Code:   "ASSISTANT.MIDDLEWARE.llm_timeout",
			Origin: OriginRemoteDependency,
			Kind:   KindTimeout,
			Nature: NatureTransient,
		},
		EntryContext{Kind: "assistant_turn", EntryID: "atn_01HRJ41Q3V000G40R40M30E209"},
		BoundaryContext{Boundary: "model_provider", Stage: "stream", RemainingBudget: 1},
	)
	if decision.Action != RecoveryActionRetry {
		t.Fatalf("Action = %s, want %s", decision.Action, RecoveryActionRetry)
	}
	if decision.DisruptionLevel != DisruptionSilent {
		t.Fatalf("DisruptionLevel = %s, want %s", decision.DisruptionLevel, DisruptionSilent)
	}
}

func TestDefaultRecoveryPolicySurfacesPermissionFailure(t *testing.T) {
	decision := DefaultRecoveryPolicy{}.Decide(
		Failure{
			Code:   "ASSISTANT.USER.permission_required",
			Origin: OriginUser,
			Kind:   KindPermission,
			Nature: NatureRequiresPermission,
		},
		EntryContext{},
		BoundaryContext{},
	)
	if decision.Action != RecoveryActionSurface {
		t.Fatalf("Action = %s, want %s", decision.Action, RecoveryActionSurface)
	}
	if decision.DisruptionLevel != DisruptionPermissionCard {
		t.Fatalf("DisruptionLevel = %s, want %s", decision.DisruptionLevel, DisruptionPermissionCard)
	}
}

func TestFailureResponseRedactsDebugByDefault(t *testing.T) {
	response := ToResponse(
		Failure{
			Code:   "ASSISTANT.SYSTEM.internal_error",
			Origin: OriginSystem,
			Kind:   KindInternal,
			Nature: NatureBug,
		},
		ResponseOptions{
			DebugMessage: "internal stack",
		},
	)
	if response.DebugMessage != "debug_message_redacted" {
		t.Fatalf("DebugMessage = %q", response.DebugMessage)
	}
}
