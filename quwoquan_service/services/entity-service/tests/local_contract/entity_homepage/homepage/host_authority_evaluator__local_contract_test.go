// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
// readiness_case: evaluate-entity-homepage-gathering-host-authority-local
package local_contract

import (
	"context"
	"testing"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

type homepageAuthorityReader struct {
	aggregate *homepagemodel.Homepage
}

func (reader homepageAuthorityReader) Load(
	context.Context,
	string,
) (*homepagemodel.Homepage, bool, error) {
	return reader.aggregate, reader.aggregate != nil, nil
}

func TestEntityHomepageHostAuthorityEvaluatorOwnsOwnerAndManagerSemantics(t *testing.T) {
	now := time.Date(2026, 8, 6, 15, 0, 0, 0, time.UTC)
	aggregate := mustAuthorityHomepage(t, homepagemodel.StatusPublished, 9)
	evaluator, err := homepageapp.NewHostAuthorityEvaluator(
		homepageAuthorityReader{aggregate: aggregate},
		func() time.Time { return now },
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, actor := range []string{"owner-persona", "manager-persona"} {
		t.Run(actor, func(t *testing.T) {
			evidence, evaluateErr := evaluator.Evaluate(
				context.Background(),
				entityAuthorityQuery(actor, 9),
			)
			if evaluateErr != nil {
				t.Fatal(evaluateErr)
			}
			if !evidence.Valid || evidence.Revoked {
				t.Fatalf("authorized Entity actor evidence=%+v", evidence)
			}
		})
	}
	for name, query := range map[string]runtimeauthority.Query{
		"forged actor":     entityAuthorityQuery("outsider", 9),
		"version mismatch": entityAuthorityQuery("owner-persona", 8),
		"subject mismatch": func() runtimeauthority.Query {
			value := entityAuthorityQuery("owner-persona", 9)
			value.HostSubjectRef = "entity_homepage:forged"
			return value
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			evidence, evaluateErr := evaluator.Evaluate(context.Background(), query)
			if evaluateErr != nil {
				t.Fatal(evaluateErr)
			}
			if evidence.Valid {
				t.Fatalf("invalid Entity query unexpectedly valid: %+v", evidence)
			}
		})
	}
}

func TestEntityHomepageHostAuthorityEvaluatorRevokesOfflineHomepage(t *testing.T) {
	aggregate := mustAuthorityHomepage(t, homepagemodel.StatusOffline, 10)
	evaluator, err := homepageapp.NewHostAuthorityEvaluator(
		homepageAuthorityReader{aggregate: aggregate},
		time.Now,
	)
	if err != nil {
		t.Fatal(err)
	}
	evidence, err := evaluator.Evaluate(
		context.Background(),
		entityAuthorityQuery("owner-persona", 10),
	)
	if err != nil {
		t.Fatal(err)
	}
	if evidence.Valid || !evidence.Revoked {
		t.Fatalf("offline Entity authority evidence=%+v", evidence)
	}
}

func mustAuthorityHomepage(
	t *testing.T,
	status homepagemodel.Status,
	version int64,
) *homepagemodel.Homepage {
	t.Helper()
	now := time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC)
	aggregate, err := homepagemodel.Restore(homepagemodel.Snapshot{
		ID: "homepage-1", Version: version, Title: "Authority Homepage",
		HomepageType: "hotel", CanonicalEntityID: "entity-1",
		ObjectPageTemplate: "standard", Status: status,
		SourceType: "claimed", ClaimStatus: "claimed",
		OwnerUserID: "account-1", OwnerPersonaID: "owner-persona",
		ManagerPersonaIDs: []string{"manager-persona"},
		CreatedAt:         now, UpdatedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	return aggregate
}

func entityAuthorityQuery(actor string, version int64) runtimeauthority.Query {
	return runtimeauthority.Query{
		HostSubjectKind: "entity_homepage", HostSubjectID: "homepage-1",
		HostSubjectRef: "entity_homepage:homepage-1",
		ActorPersonaID: actor, OrganizerPersonaID: actor,
		AuthorityEvidenceRef: "entity_homepage:homepage-1:authority:" + actor,
		AuthorityVersion:     version, Action: "publish",
	}
}
