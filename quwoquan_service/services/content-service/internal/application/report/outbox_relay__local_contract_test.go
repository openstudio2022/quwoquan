package report_test

import (
	"context"
	"errors"
	"reflect"
	"testing"
	"time"

	reportapp "quwoquan_service/services/content-service/internal/application/report"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
	"quwoquan_service/services/content-service/internal/testsupport"
)

type reportOutboxPublisherSpy struct {
	published []string
	failEvent string
}

func (p *reportOutboxPublisherSpy) Publish(
	_ context.Context,
	event reportports.OutboxEvent,
) error {
	if event.EventID == p.failEvent {
		return errors.New("simulated report publisher failure")
	}
	p.published = append(p.published, event.EventID)
	return nil
}

func TestOutboxRelayReplaysBatchAfterPublishFailureWithoutCheckpointAdvance(
	t *testing.T,
) {
	t.Parallel()

	store := testsupport.NewReportStore()
	occurredAt := time.Now().UTC().Add(-time.Second).Truncate(time.Microsecond)
	persistReportOutboxEvent(t, store, "rpt-1", "evt-1", occurredAt)
	persistReportOutboxEvent(t, store, "rpt-2", "evt-2", occurredAt.Add(time.Microsecond))

	failingPublisher := &reportOutboxPublisherSpy{failEvent: "evt-2"}
	relay := reportapp.NewOutboxRelay(
		store,
		store,
		failingPublisher,
		"moderation-projection",
	)
	delivered, err := relay.Drain(context.Background(), 10)
	if err == nil {
		t.Fatal("Drain() must report publisher failure")
	}
	if delivered != 0 {
		t.Fatalf("Drain() delivered = %d, want 0 committed facts", delivered)
	}
	if !reflect.DeepEqual(failingPublisher.published, []string{"evt-1"}) {
		t.Fatalf("published before failure = %v, want [evt-1]", failingPublisher.published)
	}

	lease, acquired, err := store.AcquireCheckpoint(
		context.Background(),
		"moderation-projection",
	)
	if err != nil {
		t.Fatalf("AcquireCheckpoint() error = %v", err)
	}
	if !acquired {
		t.Fatal("AcquireCheckpoint() must be available after failed relay")
	}
	if checkpoint := lease.Checkpoint(); checkpoint != "" {
		t.Fatalf("checkpoint after failed publish = %q, want empty", checkpoint)
	}
	if err := lease.Rollback(); err != nil {
		t.Fatalf("Rollback() error = %v", err)
	}

	replayPublisher := &reportOutboxPublisherSpy{}
	replayRelay := reportapp.NewOutboxRelay(
		store,
		store,
		replayPublisher,
		"moderation-projection",
	)
	delivered, err = replayRelay.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("replay Drain() error = %v", err)
	}
	if delivered != 2 {
		t.Fatalf("replay Drain() delivered = %d, want 2", delivered)
	}
	if !reflect.DeepEqual(replayPublisher.published, []string{"evt-1", "evt-2"}) {
		t.Fatalf("replayed events = %v, want [evt-1 evt-2]", replayPublisher.published)
	}
}

func TestOutboxRelayDoesNotRepublishCommittedCheckpoint(
	t *testing.T,
) {
	t.Parallel()

	store := testsupport.NewReportStore()
	occurredAt := time.Now().UTC().Add(-time.Second).Truncate(time.Microsecond)
	persistReportOutboxEvent(t, store, "rpt-1", "evt-1", occurredAt)
	persistReportOutboxEvent(t, store, "rpt-2", "evt-2", occurredAt.Add(time.Microsecond))

	publisher := &reportOutboxPublisherSpy{}
	relay := reportapp.NewOutboxRelay(store, store, publisher, "audit-projection")
	delivered, err := relay.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("first Drain() error = %v", err)
	}
	if delivered != 2 {
		t.Fatalf("first Drain() delivered = %d, want 2", delivered)
	}
	delivered, err = relay.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("second Drain() error = %v", err)
	}
	if delivered != 0 {
		t.Fatalf("second Drain() delivered = %d, want 0", delivered)
	}
	if !reflect.DeepEqual(publisher.published, []string{"evt-1", "evt-2"}) {
		t.Fatalf("published = %v, want exactly one delivery per fact", publisher.published)
	}
}

func TestOutboxRelayHealthRequiresBackgroundSuccessfulScan(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	relay := reportapp.NewOutboxRelay(
		store,
		store,
		&reportOutboxPublisherSpy{},
		"health-projection",
	)
	if err := relay.Healthy(time.Second); err == nil {
		t.Fatal("Healthy() must reject a relay without a completed scan")
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		done <- relay.Run(ctx, time.Millisecond)
	}()

	deadline := time.Now().Add(time.Second)
	for {
		if err := relay.Healthy(time.Second); err == nil {
			break
		}
		if time.Now().After(deadline) {
			cancel()
			<-done
			t.Fatal("Healthy() did not observe a completed background scan")
		}
		time.Sleep(time.Millisecond)
	}
	cancel()
	if err := <-done; !errors.Is(err, context.Canceled) {
		t.Fatalf("Run() error = %v, want context.Canceled", err)
	}
}

func persistReportOutboxEvent(
	t *testing.T,
	store *testsupport.ReportStore,
	reportID string,
	eventID string,
	occurredAt time.Time,
) {
	t.Helper()
	aggregate, err := reportmodel.Create(reportmodel.CreateParams{
		ID:          reportID,
		ReporterID:  "reporter-1",
		TargetType:  reportmodel.TargetPost,
		TargetID:    "post-1",
		Reason:      reportmodel.ReasonSpam,
		Description: "local-contract fixture",
		Now:         occurredAt,
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	_, err = store.Commit(context.Background(), reportports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  0,
		IdempotencyKey:   "receipt-" + eventID,
		CommandName:      "CreateReport",
		CommandDigest:    "digest-" + eventID,
		ReceiptExpiresAt: time.Now().UTC().Add(time.Hour),
		Events: []reportports.OutboxEvent{{
			EventID:          eventID,
			EventType:        "content.report.created",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          []byte(`{"kind":"report"}`),
			OccurredAt:       occurredAt,
		}},
	})
	if err != nil {
		t.Fatalf("Commit() error = %v", err)
	}
}
