// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// readiness_case: send-greeting-request-local
// readiness_case: list-greeting-inbox-local
// readiness_case: list-greeting-outbox-local
// readiness_case: reply-greeting-request-local
// readiness_case: ignore-greeting-request-local
// readiness_case: cancel-greeting-request-local
package local_contract

import (
	"context"
	"testing"
	"time"

	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingports "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
)

type facadeGreetingStore struct {
	items    map[string]*greetingmodel.GreetingRequest
	receipts map[string]*greetingmodel.GreetingRequest
}

func newFacadeGreetingStore() *facadeGreetingStore {
	return &facadeGreetingStore{
		items:    make(map[string]*greetingmodel.GreetingRequest),
		receipts: make(map[string]*greetingmodel.GreetingRequest),
	}
}

func (*facadeGreetingStore) Create(context.Context, *greetingmodel.GreetingRequest) error { return nil }
func (*facadeGreetingStore) Update(context.Context, *greetingmodel.GreetingRequest) error { return nil }

func (s *facadeGreetingStore) FindByID(_ context.Context, id string) (*greetingmodel.GreetingRequest, error) {
	return s.items[id], nil
}

func (s *facadeGreetingStore) FindPendingBetween(_ context.Context, requesterID, targetID string) (*greetingmodel.GreetingRequest, error) {
	for _, item := range s.items {
		if item.RequesterPersonaID == requesterID && item.TargetPersonaID == targetID &&
			item.Status == greetingmodel.GreetingStatusPending {
			return item, nil
		}
	}
	return nil, nil
}

func (s *facadeGreetingStore) HasPendingBetween(ctx context.Context, personaA, personaB string) (bool, error) {
	item, err := s.FindPendingBetween(ctx, personaA, personaB)
	return item != nil, err
}

func (s *facadeGreetingStore) HasRepliedBetween(_ context.Context, personaA, personaB string) (bool, error) {
	for _, item := range s.items {
		if item.RequesterPersonaID == personaA && item.TargetPersonaID == personaB &&
			item.Status == greetingmodel.GreetingStatusReplied {
			return true, nil
		}
	}
	return false, nil
}

func (s *facadeGreetingStore) ListInbox(_ context.Context, targetID, status, _ string, _ int) ([]greetingmodel.GreetingRequest, string, error) {
	return s.list(targetID, status, false), "", nil
}

func (s *facadeGreetingStore) ListOutbox(_ context.Context, requesterID, status, _ string, _ int) ([]greetingmodel.GreetingRequest, string, error) {
	return s.list(requesterID, status, true), "", nil
}

func (s *facadeGreetingStore) list(personaID, status string, outbox bool) []greetingmodel.GreetingRequest {
	items := make([]greetingmodel.GreetingRequest, 0, len(s.items))
	for _, item := range s.items {
		owner := item.TargetPersonaID
		if outbox {
			owner = item.RequesterPersonaID
		}
		if owner == personaID && (status == "" || item.Status == status) {
			items = append(items, *item)
		}
	}
	return items
}

func (s *facadeGreetingStore) MarkPendingBlockedBetween(_ context.Context, personaA, personaB string) error {
	for _, item := range s.items {
		if item.RequesterPersonaID == personaA && item.TargetPersonaID == personaB &&
			item.Status == greetingmodel.GreetingStatusPending {
			item.Status = greetingmodel.GreetingStatusBlocked
		}
	}
	return nil
}

func (s *facadeGreetingStore) LoadCommandReceipt(_ context.Context, actorID, key, operation string) (*greetingmodel.GreetingRequest, bool, error) {
	item, found := s.receipts[actorID+"|"+key+"|"+operation]
	return item, found, nil
}

func (s *facadeGreetingStore) CommitCommand(_ context.Context, commit greetingports.GreetingCommit) error {
	s.items[commit.Greeting.ID] = commit.Greeting
	if commit.IdempotencyKey != "" {
		s.receipts[commit.ActorPersonaID+"|"+commit.IdempotencyKey+"|"+commit.Operation] = commit.Greeting
	}
	return nil
}

func (s *facadeGreetingStore) CountRecentByRequester(_ context.Context, requesterID string, _ time.Duration) (int64, error) {
	var count int64
	for _, item := range s.items {
		if item.RequesterPersonaID == requesterID {
			count++
		}
	}
	return count, nil
}

func TestGreetingRequestFacadeLifecycleAndQueries(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := newFacadeGreetingStore()
	service := greetingapp.NewGreetingService(
		store,
		store,
		failOpenRelationships{},
		failOpenConversationGateway{},
		failOpenEventPublisher{},
		failOpenGreetingStream{},
		allowGreetingPolicy{},
	)
	send := func(key string) *greetingmodel.GreetingRequest {
		item, err := service.Send(ctx, greetingapp.SendGreetingRequest{
			RequesterPersonaID: "requester",
			TargetPersonaID:    "target",
			RequestMessage:     "你好",
			Source:             "profile",
			IdempotencyKey:     key,
		})
		if err != nil {
			t.Fatalf("SendGreetingRequest(%s): %v", key, err)
		}
		return item
	}

	first := send("send-1")
	inbox, _, err := service.ListInbox(ctx, "target", "pending", "", 20)
	if err != nil || len(inbox) != 1 || inbox[0].ID != first.ID {
		t.Fatalf("ListGreetingInbox: items=%+v err=%v", inbox, err)
	}
	outbox, _, err := service.ListOutbox(ctx, "requester", "pending", "", 20)
	if err != nil || len(outbox) != 1 || outbox[0].ID != first.ID {
		t.Fatalf("ListGreetingOutbox: items=%+v err=%v", outbox, err)
	}
	replied, err := service.Reply(ctx, "target", first.ID, "reply-1")
	if err != nil || replied.Status != greetingmodel.GreetingStatusReplied {
		t.Fatalf("ReplyGreetingRequest: item=%+v err=%v", replied, err)
	}

	second := send("send-2")
	ignored, err := service.Ignore(ctx, "target", second.ID, "ignore-1")
	if err != nil || ignored.Status != greetingmodel.GreetingStatusIgnored {
		t.Fatalf("IgnoreGreetingRequest: item=%+v err=%v", ignored, err)
	}

	third := send("send-3")
	cancelled, err := service.Cancel(ctx, "requester", third.ID, "cancel-1")
	if err != nil || cancelled.Status != greetingmodel.GreetingStatusCancelled {
		t.Fatalf("CancelGreetingRequest: item=%+v err=%v", cancelled, err)
	}
}
