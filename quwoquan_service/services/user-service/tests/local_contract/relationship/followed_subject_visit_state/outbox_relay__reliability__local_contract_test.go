package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	visitports "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/ports"
)

// stubVisitOutbox 是端口级替身，只覆盖 relay 的投递语义；事务性由
// tests/api_integration 下的真实 mongod 测试证明。
type stubVisitOutbox struct {
	pending   []visitmodel.OutboxEvent
	published []string
	released  []string
	markErr   error
}

func (s *stubVisitOutbox) ClaimPendingOutbox(
	_ context.Context,
	ownerID string,
	_ time.Duration,
	limit int,
) ([]visitmodel.OutboxEvent, error) {
	if ownerID == "" {
		return nil, errors.New("owner is required")
	}
	if limit > len(s.pending) {
		limit = len(s.pending)
	}
	claimed := s.pending[:limit]
	s.pending = s.pending[limit:]
	return claimed, nil
}

func (s *stubVisitOutbox) MarkOutboxPublished(_ context.Context, eventID, _ string) error {
	if s.markErr != nil {
		return s.markErr
	}
	s.published = append(s.published, eventID)
	return nil
}

func (s *stubVisitOutbox) ReleaseOutboxClaim(_ context.Context, eventID, _ string) error {
	s.released = append(s.released, eventID)
	return nil
}

type stubVisitPublisher struct {
	delivered []visitmodel.OutboxEvent
	failOn    string
}

func (s *stubVisitPublisher) PublishFollowedSubjectVisited(
	_ context.Context,
	event visitmodel.OutboxEvent,
) error {
	if event.EventID == s.failOn {
		return errors.New("transport unavailable")
	}
	s.delivered = append(s.delivered, event)
	return nil
}

func visitEvent(clientRequestID string) visitmodel.OutboxEvent {
	command := visitmodel.MarkVisitedCommand{
		PersonaID:       "persona-viewer",
		SubjectType:     "homepage",
		SubjectID:       "homepage-1",
		ClientRequestID: clientRequestID,
	}
	return visitmodel.OutboxEvent{
		EventID:     visitmodel.VisitEventID(command),
		AggregateID: visitmodel.VisitAggregateID(command.PersonaID, command.SubjectType, command.SubjectID),
		EventName:   visitmodel.EventFollowedSubjectVisited,
		Payload: visitmodel.EventPayload{
			PersonaID:   command.PersonaID,
			SubjectType: command.SubjectType,
			SubjectID:   command.SubjectID,
		},
	}
}

func TestFollowedSubjectVisitOutboxRelayPublishesThenAcknowledges(t *testing.T) {
	outbox := &stubVisitOutbox{pending: []visitmodel.OutboxEvent{visitEvent("r1"), visitEvent("r2")}}
	publisher := &stubVisitPublisher{}
	drained, err := visitapp.NewOutboxRelay(outbox, publisher).Drain(context.Background(), 10)
	if err != nil || drained != 2 {
		t.Fatalf("drain: drained=%d err=%v", drained, err)
	}
	if len(publisher.delivered) != 2 {
		t.Fatalf("expected both events delivered, got %d", len(publisher.delivered))
	}
	if len(outbox.published) != 2 {
		t.Fatalf("expected both events acknowledged, got %v", outbox.published)
	}
}

// 投递失败必须释放租约且不确认，事件留在 outbox 等待下一轮 relay 重放。
func TestFollowedSubjectVisitOutboxRelayReleasesClaimOnPublishFailure(t *testing.T) {
	failing := visitEvent("r1")
	outbox := &stubVisitOutbox{pending: []visitmodel.OutboxEvent{failing}}
	publisher := &stubVisitPublisher{failOn: failing.EventID}
	drained, err := visitapp.NewOutboxRelay(outbox, publisher).Drain(context.Background(), 10)
	if err == nil {
		t.Fatal("expected publish failure to surface")
	}
	if drained != 0 {
		t.Fatalf("failed publish must not count as drained, got %d", drained)
	}
	if len(outbox.published) != 0 {
		t.Fatalf("failed publish must not acknowledge, got %v", outbox.published)
	}
	if len(outbox.released) != 1 || outbox.released[0] != failing.EventID {
		t.Fatalf("expected claim release for %q, got %v", failing.EventID, outbox.released)
	}
}

// 租约被抢走时当前 relay 只跳过该事件，由新持有者投递，不得中断整批。
func TestFollowedSubjectVisitOutboxRelaySkipsLostClaim(t *testing.T) {
	outbox := &stubVisitOutbox{
		pending: []visitmodel.OutboxEvent{visitEvent("r1")},
		markErr: visitports.ErrOutboxClaimLost,
	}
	publisher := &stubVisitPublisher{}
	drained, err := visitapp.NewOutboxRelay(outbox, publisher).Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("lost claim must not fail the drain: %v", err)
	}
	if drained != 0 {
		t.Fatalf("lost claim must not count as published, got %d", drained)
	}
}

// eventId 只由命令身份派生，重放同一 clientRequestId 不会产生第二个事件标识。
func TestFollowedSubjectVisitEventIDIsDerivedFromCommandIdentity(t *testing.T) {
	command, err := visitmodel.NewMarkVisitedCommand(
		"persona-viewer", "homepage", "homepage-1", time.Now().UTC(), "request-1",
	)
	if err != nil {
		t.Fatalf("build command: %v", err)
	}
	if visitmodel.VisitEventID(command) != visitmodel.VisitEventID(command) {
		t.Fatal("event id must be stable for the same command")
	}
	other, err := visitmodel.NewMarkVisitedCommand(
		"persona-viewer", "homepage", "homepage-1", time.Now().UTC(), "request-2",
	)
	if err != nil {
		t.Fatalf("build command: %v", err)
	}
	if visitmodel.VisitEventID(command) == visitmodel.VisitEventID(other) {
		t.Fatal("distinct client requests must produce distinct event ids")
	}
}
