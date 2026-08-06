package application_test

import (
	"context"
	"testing"
	"time"

	operation "quwoquan_service/runtime/operation"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

func TestScopeCPrepareCreationUsesTrustedActorAndTypedOwnerDecision(t *testing.T) {
	facade := app.NewHostOutcomeFacade(
		scopeCHostUnusedAggregateStore{},
		scopeCHostAuthorityReader{valid: true},
	)
	now := time.Now().UTC()
	result, err := facade.PrepareCreation(scopeCHostOperationContext("creator-persona"), app.PrepareHostCommand{
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindCircle,
			HostSubjectID:        "circle-host",
			AuthorityEvidenceRef: "circle-authority/9",
			AuthorityVersion:     9,
			AuthorityExpiresAt:   now.Add(time.Hour),
		},
	})
	if err != nil {
		t.Fatalf("prepare creation: %v", err)
	}
	if len(result.OrganizerAssignments) != 1 ||
		result.OrganizerAssignments[0].PersonaID != "creator-persona" ||
		result.OrganizerAssignments[0].Role != contract.GatheringOrganizerRolePrimaryOrganizer {
		t.Fatalf("trusted creator was not assigned as primary organizer: %+v", result)
	}
	if result.HostBinding.HostSubjectID == result.OrganizerAssignments[0].PersonaID {
		t.Fatalf("HostBinding was collapsed into createdByPersonaId: %+v", result)
	}
}

func TestScopeCPrepareCreationFailsClosedOnRevokedOwnerDecision(t *testing.T) {
	facade := app.NewHostOutcomeFacade(
		scopeCHostUnusedAggregateStore{},
		scopeCHostAuthorityReader{valid: true, revoked: true},
	)
	now := time.Now().UTC()
	_, err := facade.PrepareCreation(scopeCHostOperationContext("creator-persona"), app.PrepareHostCommand{
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindEntityHomepage,
			HostSubjectID:        "entity-host",
			AuthorityEvidenceRef: "entity-authority/3",
			AuthorityVersion:     3,
			AuthorityExpiresAt:   now.Add(time.Hour),
		},
	})
	if err == nil {
		t.Fatal("revoked canonical owner decision unexpectedly prepared creation")
	}
}

func TestScopeCCreatorOrganizerDoesNotOccupySeatWithoutExplicitParticipation(t *testing.T) {
	facade := app.NewHostOutcomeFacade(
		scopeCHostUnusedAggregateStore{},
		scopeCHostAuthorityReader{valid: true},
	)
	now := time.Now().UTC()
	current := contract.Gathering{
		ID: "gathering-1",
		PolicySet: contract.GatheringPolicySet{
			CapacityPolicy: contract.GatheringCapacityPolicy{MaxParticipants: 2},
		},
		CurrentGatheringRevisionID:     "revision-1",
		CurrentGatheringRevisionNumber: 1,
		Revisions: []contract.GatheringRevision{{
			RevisionID: "revision-1", RevisionNumber: 1, Digest: "digest-1",
		}},
	}
	if err := facade.InitializeCreatorParticipation(
		&current,
		"creator-persona",
		false,
		now,
	); err != nil {
		t.Fatalf("initialize non-participating creator: %v", err)
	}
	if len(current.Participations) != 0 {
		t.Fatalf("organizer authority implicitly occupied a seat: %+v", current.Participations)
	}
	if err := facade.InitializeCreatorParticipation(
		&current,
		"creator-persona",
		true,
		now,
	); err != nil {
		t.Fatalf("initialize explicitly participating creator: %v", err)
	}
	if len(current.Participations) != 1 ||
		current.Participations[0].State != contract.GatheringParticipationStateActive {
		t.Fatalf("explicit creator participation was not separate: %+v", current.Participations)
	}
}

func TestScopeCAcknowledgeRevisionFacadeUsesParticipationCAS(t *testing.T) {
	now := time.Now().UTC()
	store := newMemoryStore()
	current := scopeBApplicationGathering(
		now,
		contract.GatheringAdmissionPolicyOpen,
		2,
	)
	current.CurrentGatheringRevisionID = "revision-2"
	current.CurrentGatheringRevisionNumber = 2
	current.Participations = []contract.GatheringParticipation{{
		GatheringID:     current.ID,
		PersonaID:       "persona-member",
		State:           contract.GatheringParticipationStateActive,
		AdmissionSource: contract.GatheringAdmissionSourceOpen,
		Version:         4,
		CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
			RevisionID:     "revision-2",
			RevisionNumber: 2,
			RevisionDigest: "revision-digest-2",
			Status:         contract.GatheringRevisionAcknowledgementStatusPending,
			DeadlineAt:     now.Add(time.Hour),
		},
	}}
	store.value = &current
	facade := app.NewHostOutcomeFacade(
		store,
		scopeCHostAuthorityReader{valid: true},
	)
	result, err := facade.AcknowledgeRevision(
		commandContext("persona-member", "scope-c-acknowledge"),
		app.AcknowledgeRevisionCommand{
			GatheringID:                  current.ID,
			RevisionID:                   "revision-2",
			RevisionDigest:               "revision-digest-2",
			Decision:                     gatheringclient.GatheringRevisionAcknowledgementDecisionAccept,
			ExpectedGatheringVersion:     current.Version,
			ExpectedParticipationVersion: 4,
		},
	)
	if err != nil {
		t.Fatalf("AcknowledgeRevision: %v", err)
	}
	stored := store.mustLoad(t)
	if result.AggregateVersion != current.Version+1 ||
		stored.Participations[0].Version != 5 ||
		stored.Participations[0].CurrentChangeAcknowledgement.Status !=
			contract.GatheringRevisionAcknowledgementStatusAccepted {
		t.Fatalf(
			"acknowledgement result=%+v stored=%+v",
			result,
			stored.Participations,
		)
	}
}

type scopeCHostAuthorityReader struct {
	valid   bool
	revoked bool
}

func (reader scopeCHostAuthorityReader) ReadHostAuthority(
	_ context.Context,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
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
		Valid:                reader.valid,
		Revoked:              reader.revoked,
		ExpiresAt:            query.EvaluatedAt.Add(time.Hour),
	}, nil
}

type scopeCHostUnusedAggregateStore struct{}

func (scopeCHostUnusedAggregateStore) Load(
	context.Context,
	string,
) (contract.Gathering, bool, error) {
	panic("PrepareCreation must not load an aggregate")
}

func (scopeCHostUnusedAggregateStore) Commit(
	context.Context,
	ports.CommitRequest,
) (ports.CommitReceipt, error) {
	panic("PrepareCreation must not commit before lifecycle Create")
}

func scopeCHostOperationContext(personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "CreateGatheringDraft",
		RequestID:      "scope-c-request",
		TraceID:        "scope-c-trace",
		IdempotencyKey: "scope-c-idempotency",
		Actor:          operation.ActorContext{PersonaID: personaID},
	})
}
