package external_test

import (
	"context"
	"errors"
	"testing"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	external "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

func TestScopeCHostAuthorityReaderDispatchesByCanonicalSubjectKind(t *testing.T) {
	for subjectKind, expectedClient := range map[contract.GatheringHostSubjectKind]string{
		contract.GatheringHostSubjectKindPersona:        "persona",
		contract.GatheringHostSubjectKindEntityHomepage: "entity_homepage",
		contract.GatheringHostSubjectKindCircle:         "circle",
	} {
		calls := make(map[string]int)
		reader := external.NewHostAuthorityReader(
			scopeCHostAuthorityPersonaClient{calls: calls},
			scopeCHostAuthorityEntityClient{calls: calls},
			scopeCHostAuthorityCircleClient{calls: calls},
		)
		query := scopeCHostAuthorityQuery(subjectKind)
		evidence, err := reader.ReadHostAuthority(context.Background(), query)
		if err != nil {
			t.Fatalf("kind %q: read authority: %v", subjectKind, err)
		}
		if calls[expectedClient] != 1 || len(calls) != 1 {
			t.Fatalf("kind %q dispatched to wrong owners: %+v", subjectKind, calls)
		}
		if evidence.Action != query.Action ||
			evidence.AuthorityEvidenceRef != query.AuthorityEvidenceRef {
			t.Fatalf("kind %q returned untyped evidence: %+v", subjectKind, evidence)
		}
	}
}

func TestScopeCHostAuthorityReaderRejectsMismatchedOwnerResponse(t *testing.T) {
	reader := external.NewHostAuthorityReader(
		scopeCHostAuthorityPersonaClient{forgeActor: true},
		scopeCHostAuthorityEntityClient{},
		scopeCHostAuthorityCircleClient{},
	)
	_, err := reader.ReadHostAuthority(
		context.Background(),
		scopeCHostAuthorityQuery(contract.GatheringHostSubjectKindPersona),
	)
	if !errors.Is(err, gatheringapp.ErrHostAuthorityUnavailable) {
		t.Fatalf("expected fail-closed owner response error, got %v", err)
	}
}

type scopeCHostAuthorityPersonaClient struct {
	calls      map[string]int
	forgeActor bool
}

func (client scopeCHostAuthorityPersonaClient) EvaluatePersonaHostAuthority(
	_ context.Context,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
	if client.calls != nil {
		client.calls["persona"]++
	}
	evidence := scopeCHostAuthorityEchoEvidence(query)
	if client.forgeActor {
		evidence.ActorPersonaID = "attacker"
	}
	return evidence, nil
}

type scopeCHostAuthorityEntityClient struct{ calls map[string]int }

func (client scopeCHostAuthorityEntityClient) EvaluateEntityHomepageHostAuthority(
	_ context.Context,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
	if client.calls != nil {
		client.calls["entity_homepage"]++
	}
	return scopeCHostAuthorityEchoEvidence(query), nil
}

type scopeCHostAuthorityCircleClient struct{ calls map[string]int }

func (client scopeCHostAuthorityCircleClient) EvaluateCircleHostAuthority(
	_ context.Context,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
	if client.calls != nil {
		client.calls["circle"]++
	}
	return scopeCHostAuthorityEchoEvidence(query), nil
}

func scopeCHostAuthorityQuery(
	subjectKind contract.GatheringHostSubjectKind,
) model.HostAuthorityQuery {
	return model.HostAuthorityQuery{
		HostSubjectKind:      subjectKind,
		HostSubjectID:        "host-subject",
		ActorPersonaID:       "primary",
		OrganizerPersonaID:   "candidate",
		AuthorityEvidenceRef: "authority/11",
		AuthorityVersion:     11,
		Action:               model.HostAuthorityTransferOrganizer,
		EvaluatedAt:          time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC),
	}
}

func scopeCHostAuthorityEchoEvidence(
	query model.HostAuthorityQuery,
) model.HostAuthorityEvidence {
	return model.HostAuthorityEvidence{
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		HostReference:        string(query.HostSubjectKind) + ":" + query.HostSubjectID,
		ActorPersonaID:       query.ActorPersonaID,
		OrganizerPersonaID:   query.OrganizerPersonaID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		AuthorityDigest:      "sha256:ea13d8077a78b70e28c40273c4d1a7e6c833f3493bbb7419112b1d9fde8cbc9b",
		Action:               query.Action,
		Valid:                true,
		ExpiresAt:            query.EvaluatedAt.Add(time.Hour),
	}
}
