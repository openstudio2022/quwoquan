// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingports "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
	relationshipmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type failOpenGreetingStore struct{}

func (failOpenGreetingStore) Create(context.Context, *greetingmodel.GreetingRequest) error {
	return nil
}
func (failOpenGreetingStore) Update(context.Context, *greetingmodel.GreetingRequest) error {
	return nil
}
func (failOpenGreetingStore) FindByID(context.Context, string) (*greetingmodel.GreetingRequest, error) {
	return nil, nil
}
func (failOpenGreetingStore) FindPendingBetween(context.Context, string, string) (*greetingmodel.GreetingRequest, error) {
	return nil, nil
}
func (failOpenGreetingStore) HasPendingBetween(context.Context, string, string) (bool, error) {
	return false, nil
}
func (failOpenGreetingStore) HasRepliedBetween(context.Context, string, string) (bool, error) {
	return false, nil
}
func (failOpenGreetingStore) ListInbox(context.Context, string, string, string, int) ([]greetingmodel.GreetingRequest, string, error) {
	return nil, "", nil
}
func (failOpenGreetingStore) ListOutbox(context.Context, string, string, string, int) ([]greetingmodel.GreetingRequest, string, error) {
	return nil, "", nil
}
func (failOpenGreetingStore) MarkPendingBlockedBetween(context.Context, string, string) error {
	return nil
}

type failOpenGreetingCommands struct {
	committed *greetingmodel.GreetingRequest
	commit    *greetingports.GreetingCommit
}

func (*failOpenGreetingCommands) LoadCommandReceipt(context.Context, string, string, string) (*greetingmodel.GreetingRequest, bool, error) {
	return nil, false, nil
}
func (s *failOpenGreetingCommands) CommitCommand(_ context.Context, commit greetingports.GreetingCommit) error {
	s.committed = commit.Greeting
	s.commit = &commit
	return nil
}
func (*failOpenGreetingCommands) CountRecentByRequester(context.Context, string, time.Duration) (int64, error) {
	return 0, nil
}

type failOpenRelationships struct{}

func (failOpenRelationships) GetRelationship(context.Context, string, string) (relationshipmodel.RelationshipState, error) {
	return relationshipmodel.RelationshipState{}, nil
}

type failOpenConversationGateway struct{}

func (failOpenConversationGateway) PromoteGreetingToDirect(context.Context, string, string, greetingapp.GreetingPromotion) (string, error) {
	return "", nil
}
func (failOpenConversationGateway) HasDirectBetween(context.Context, string, string) (bool, error) {
	return false, nil
}

type failOpenEventPublisher struct{}

func (failOpenEventPublisher) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

type failOpenGreetingStream struct{}

func (failOpenGreetingStream) PublishGreetingEvent(context.Context, greetingapp.GreetingStreamEvent) error {
	return nil
}

type allowGreetingPolicy struct{}

func (allowGreetingPolicy) AllowsStrangerGreeting(context.Context, string) (bool, error) {
	return true, nil
}

type recordingGreetingPolicy struct{ accountID string }

func (policy *recordingGreetingPolicy) AllowsStrangerGreeting(
	_ context.Context,
	accountID string,
) (bool, error) {
	policy.accountID = accountID
	return true, nil
}

type staticGreetingRecipientAccounts map[string]string

func (accounts staticGreetingRecipientAccounts) ResolveOwnerAccountID(
	_ context.Context,
	personaID string,
) (string, bool, error) {
	accountID, found := accounts[personaID]
	return accountID, found, nil
}

type unavailableGreetingIntersection struct{}

func (unavailableGreetingIntersection) ResolveGreetingIntersection(
	context.Context,
	string,
	string,
	greetingmodel.GreetingIntersectionRef,
) (*greetingmodel.GreetingIntersectionSnapshot, error) {
	return nil, errors.New("content intersection unavailable")
}

func TestGreetingIntersectionResolutionFailureDegradesToOrdinaryGreeting(t *testing.T) {
	t.Parallel()
	commands := &failOpenGreetingCommands{}
	policy := &recordingGreetingPolicy{}
	service := greetingapp.NewGreetingService(
		failOpenGreetingStore{},
		commands,
		failOpenRelationships{},
		failOpenConversationGateway{},
		failOpenEventPublisher{},
		failOpenGreetingStream{},
		staticGreetingRecipientAccounts{"persona-b": "account-b"},
		policy,
		unavailableGreetingIntersection{},
	)
	created, err := service.Send(context.Background(), greetingapp.SendGreetingRequest{
		RequesterPersonaID: "persona-a",
		TargetPersonaID:    "persona-b",
		RequestMessage:     "认识一下",
		IdempotencyKey:     "greeting-fail-open-1",
		IntersectionRef: &greetingmodel.GreetingIntersectionRef{
			IntersectionID: "intersection-1",
			EvidenceID:     "evidence-1",
			SourceRef:      "coVisitedEntity",
			ObjectTypeRef:  "user",
			ObjectID:       "persona-b",
		},
	})
	if err != nil {
		t.Fatalf("ordinary greeting must still be committed: %v", err)
	}
	if created == nil || commands.committed == nil {
		t.Fatal("greeting was not committed")
	}
	if len(created.IntersectionRef) == 0 {
		t.Fatal("original typed intent reference must remain auditable")
	}
	if len(created.IntersectionSnapshot) != 0 {
		t.Fatalf("failed resolution must not freeze client facts: %s", created.IntersectionSnapshot)
	}
	if commands.commit == nil ||
		commands.commit.EventPayload["recipientAccountId"] != "account-b" {
		t.Fatalf("GreetingRequestSent did not freeze recipient AccountID: %+v", commands.commit)
	}
	if policy.accountID != "account-b" {
		t.Fatalf("notification policy read %q, want canonical AccountID", policy.accountID)
	}
}

func TestGreetingSendRejectsTargetWithoutCanonicalRecipientAccount(t *testing.T) {
	t.Parallel()
	commands := &failOpenGreetingCommands{}
	service := greetingapp.NewGreetingService(
		failOpenGreetingStore{},
		commands,
		failOpenRelationships{},
		failOpenConversationGateway{},
		failOpenEventPublisher{},
		failOpenGreetingStream{},
		staticGreetingRecipientAccounts{},
		allowGreetingPolicy{},
	)

	created, err := service.Send(context.Background(), greetingapp.SendGreetingRequest{
		RequesterPersonaID: "persona-a",
		TargetPersonaID:    "persona-b",
		RequestMessage:     "认识一下",
		IdempotencyKey:     "greeting-missing-account-1",
	})
	if err == nil || created != nil {
		t.Fatalf("missing recipient account must fail closed: created=%+v err=%v", created, err)
	}
	if commands.commit != nil {
		t.Fatalf("missing recipient account must not commit greeting: %+v", commands.commit)
	}
}
