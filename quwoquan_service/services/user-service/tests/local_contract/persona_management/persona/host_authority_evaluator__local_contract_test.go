// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
// readiness_case: evaluate-persona-gathering-host-authority-local
package local_contract

import (
	"context"
	"testing"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
)

type personaAuthorityReader struct {
	snapshot personaapp.HostAuthoritySnapshot
	found    bool
}

func (reader personaAuthorityReader) ReadHostAuthoritySnapshot(
	context.Context,
	string,
) (personaapp.HostAuthoritySnapshot, bool, error) {
	return reader.snapshot, reader.found, nil
}

func TestPersonaHostAuthorityEvaluatorRequiresActiveSelfAndExactEvidence(t *testing.T) {
	now := time.Date(2026, 8, 6, 15, 0, 0, 0, time.UTC)
	evaluator, err := personaapp.NewHostAuthorityEvaluator(personaAuthorityReader{
		snapshot: personaapp.HostAuthoritySnapshot{
			PersonaID: "persona-1", Version: 7, Status: "active",
		},
		found: true,
	}, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	base := runtimeauthority.Query{
		HostSubjectKind: "persona", HostSubjectID: "persona-1",
		HostSubjectRef: "persona:persona-1",
		ActorPersonaID: "persona-1", OrganizerPersonaID: "persona-1",
		AuthorityEvidenceRef: "persona:persona-1:self",
		AuthorityVersion:     7, Action: "create_draft",
	}
	valid, err := evaluator.Evaluate(context.Background(), base)
	if err != nil {
		t.Fatal(err)
	}
	if !valid.Valid || valid.Revoked || valid.AuthorityDigest == "" ||
		!valid.ExpiresAt.After(now) {
		t.Fatalf("valid self evidence=%+v", valid)
	}

	for name, mutate := range map[string]func(*runtimeauthority.Query){
		"forged actor": func(query *runtimeauthority.Query) {
			query.ActorPersonaID = "persona-forged"
		},
		"forged subject": func(query *runtimeauthority.Query) {
			query.HostSubjectRef = "persona:persona-forged"
		},
		"version mismatch": func(query *runtimeauthority.Query) {
			query.AuthorityVersion = 6
		},
		"action mismatch": func(query *runtimeauthority.Query) {
			query.Action = "unknown"
		},
	} {
		t.Run(name, func(t *testing.T) {
			query := base
			mutate(&query)
			evidence, evaluateErr := evaluator.Evaluate(context.Background(), query)
			if evaluateErr != nil {
				t.Fatal(evaluateErr)
			}
			if evidence.Valid {
				t.Fatalf("forged query unexpectedly valid: %+v", evidence)
			}
		})
	}
}

func TestPersonaHostAuthorityEvaluatorMarksRetiredAuthorityRevoked(t *testing.T) {
	evaluator, err := personaapp.NewHostAuthorityEvaluator(personaAuthorityReader{
		snapshot: personaapp.HostAuthoritySnapshot{
			PersonaID: "persona-1", Version: 8, Status: "retired",
		},
		found: true,
	}, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	evidence, err := evaluator.Evaluate(context.Background(), runtimeauthority.Query{
		HostSubjectKind: "persona", HostSubjectID: "persona-1",
		HostSubjectRef: "persona:persona-1",
		ActorPersonaID: "persona-1", OrganizerPersonaID: "persona-1",
		AuthorityEvidenceRef: "persona:persona-1:self",
		AuthorityVersion:     8, Action: "publish",
	})
	if err != nil {
		t.Fatal(err)
	}
	if evidence.Valid || !evidence.Revoked {
		t.Fatalf("retired Persona evidence=%+v", evidence)
	}
}
