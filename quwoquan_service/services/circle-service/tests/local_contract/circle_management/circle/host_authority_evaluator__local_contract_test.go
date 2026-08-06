package local_contract

import (
	"context"
	"testing"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

type circleAuthorityReader struct {
	circle circlemodel.Circle
	found  bool
}

func (reader circleAuthorityReader) Load(
	context.Context,
	string,
) (circlemodel.Circle, bool, error) {
	return reader.circle, reader.found, nil
}

type membershipAuthorityReader struct {
	byPersona map[string]membershipmodel.CircleMembership
}

func (reader membershipAuthorityReader) LoadByIdentity(
	_ context.Context,
	_ string,
	personaID string,
) (membershipmodel.CircleMembership, bool, error) {
	membership, found := reader.byPersona[personaID]
	return membership, found, nil
}

func TestCircleHostAuthorityEvaluatorOwnsOwnerAndAdminSemantics(t *testing.T) {
	evaluator, err := circleapp.NewHostAuthorityEvaluator(
		circleAuthorityReader{circle: circlemodel.Circle{
			ID: "circle-1", OwnerID: "owner-persona", Version: 11,
			Status: circlemodel.CircleStatusActive,
		}, found: true},
		membershipAuthorityReader{byPersona: map[string]membershipmodel.CircleMembership{
			"admin-persona": {
				ID: "membership-admin", CircleID: "circle-1",
				PersonaID: "admin-persona", Version: 4,
				Role:  membershipmodel.CircleMemberRoleAdmin,
				State: membershipmodel.CircleMembershipStateActive,
			},
			"member-persona": {
				ID: "membership-member", CircleID: "circle-1",
				PersonaID: "member-persona", Version: 3,
				Role:  membershipmodel.CircleMemberRoleMember,
				State: membershipmodel.CircleMembershipStateActive,
			},
		}},
		func() time.Time {
			return time.Date(2026, 8, 6, 15, 0, 0, 0, time.UTC)
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	for actor, version := range map[string]int64{
		"owner-persona": 11,
		"admin-persona": 4,
	} {
		t.Run(actor, func(t *testing.T) {
			evidence, evaluateErr := evaluator.Evaluate(
				context.Background(),
				circleAuthorityQuery(actor, version),
			)
			if evaluateErr != nil {
				t.Fatal(evaluateErr)
			}
			if !evidence.Valid || evidence.Revoked {
				t.Fatalf("authorized Circle actor evidence=%+v", evidence)
			}
		})
	}
	for name, query := range map[string]runtimeauthority.Query{
		"ordinary member":  circleAuthorityQuery("member-persona", 3),
		"forged actor":     circleAuthorityQuery("outsider", 11),
		"version mismatch": circleAuthorityQuery("owner-persona", 10),
		"action mismatch": func() runtimeauthority.Query {
			value := circleAuthorityQuery("owner-persona", 11)
			value.Action = "unknown"
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			evidence, evaluateErr := evaluator.Evaluate(context.Background(), query)
			if evaluateErr != nil {
				t.Fatal(evaluateErr)
			}
			if evidence.Valid {
				t.Fatalf("invalid Circle query unexpectedly valid: %+v", evidence)
			}
		})
	}
}

func TestCircleHostAuthorityEvaluatorRevokesArchivedCircle(t *testing.T) {
	evaluator, err := circleapp.NewHostAuthorityEvaluator(
		circleAuthorityReader{circle: circlemodel.Circle{
			ID: "circle-1", OwnerID: "owner-persona", Version: 12,
			Status: circlemodel.CircleStatusArchived,
		}, found: true},
		membershipAuthorityReader{},
		time.Now,
	)
	if err != nil {
		t.Fatal(err)
	}
	evidence, err := evaluator.Evaluate(
		context.Background(),
		circleAuthorityQuery("owner-persona", 12),
	)
	if err != nil {
		t.Fatal(err)
	}
	if evidence.Valid || !evidence.Revoked {
		t.Fatalf("archived Circle evidence=%+v", evidence)
	}
}

func circleAuthorityQuery(actor string, version int64) runtimeauthority.Query {
	return runtimeauthority.Query{
		HostSubjectKind: "circle", HostSubjectID: "circle-1",
		HostSubjectRef: "circle:circle-1",
		ActorPersonaID: actor, OrganizerPersonaID: actor,
		AuthorityEvidenceRef: "circle:circle-1:authority:" + actor,
		AuthorityVersion:     version, Action: "create_draft",
	}
}
