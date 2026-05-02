package personarollout

import "testing"

func TestBuildMigrationPlanResolvesHandleConflictsAndInheritsPrimaryContacts(t *testing.T) {
	plan := BuildMigrationPlan(Input{
		ReservedHandles: []string{"alice"},
		Personas: []CurrentPersona{
			{
				UserID:    "user_1",
				PersonaID: "persona_primary",
				Username:  "alice",
				Nickname:  "Alice",
				Phone:     "13800000000",
				Email:     "alice@example.com",
				IsPrimary: true,
			},
			{
				UserID:    "user_1",
				PersonaID: "persona_sidecar",
				Username:  "alice",
				Nickname:  "Alice Sidecar",
			},
		},
	})

	if got := len(plan.Personas); got != 2 {
		t.Fatalf("expected 2 planned personas, got %d", got)
	}
	if got := plan.Personas[0].UserHandle; got != "alice.persona_primary" {
		t.Fatalf("expected resolved primary handle, got %q", got)
	}
	if got := plan.Personas[1].UserHandle; got != "alice.persona_sidecar" {
		t.Fatalf("expected resolved sidecar handle, got %q", got)
	}
	if got := plan.Personas[1].Phone; got != "13800000000" {
		t.Fatalf("expected inherited phone, got %q", got)
	}
	if got := plan.Personas[1].Email; got != "alice@example.com" {
		t.Fatalf("expected inherited email, got %q", got)
	}
	if got := len(plan.Conflicts); got != 2 {
		t.Fatalf("expected 2 handle conflicts, got %d", got)
	}
}

func TestValidatePlanDetectsPublicLeakageAndMissingIdentity(t *testing.T) {
	plan := BuildMigrationPlan(Input{
		Personas: []CurrentPersona{
			{
				UserID:            "",
				PersonaID:         "persona_1",
				Username:          "alpha",
				ContentSubjectIDs: []string{"content_1", ""},
				IsPrimary:         true,
			},
		},
	})

	report := ValidatePlan(plan, Input{
		PublicSamples: []PublicSample{
			{
				Surface: "public_profile",
				Payload: map[string]any{
					"ownerUserId": "user_hidden",
				},
			},
		},
	})

	if report.PersonaMigrationFailedCount != 1 {
		t.Fatalf("expected 1 migration failure, got %d", report.PersonaMigrationFailedCount)
	}
	if report.PersonaAttributionMismatchCount != 1 {
		t.Fatalf("expected 1 attribution mismatch, got %d", report.PersonaAttributionMismatchCount)
	}
	if report.PersonaPublicLeakageCount != 1 {
		t.Fatalf("expected 1 public leakage, got %d", report.PersonaPublicLeakageCount)
	}
}

func TestBuildAcceptanceMetricsUsesReportValues(t *testing.T) {
	metrics := BuildAcceptanceMetrics(42.5, ValidationReport{
		PersonaMigrationFailedCount:     3,
		PersonaAttributionMismatchCount: 2,
		PersonaPublicLeakageCount:       1,
	})

	if metrics[MetricPersonaSwitchLatencyMs] != 42.5 {
		t.Fatalf("expected switch latency metric to be preserved, got %v", metrics[MetricPersonaSwitchLatencyMs])
	}
	if metrics[MetricPersonaMigrationFailedCount] != 3 {
		t.Fatalf("expected migration failed metric, got %v", metrics[MetricPersonaMigrationFailedCount])
	}
	if metrics[MetricPersonaAttributionMismatchCount] != 2 {
		t.Fatalf("expected attribution mismatch metric, got %v", metrics[MetricPersonaAttributionMismatchCount])
	}
	if metrics[MetricPersonaPublicLeakageCount] != 1 {
		t.Fatalf("expected public leakage metric, got %v", metrics[MetricPersonaPublicLeakageCount])
	}
}
