package persistence_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	reportapp "quwoquan_service/services/entity-service/internal/application/homepage_status_report"
	reportmodel "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model"
	reportports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
	"quwoquan_service/services/entity-service/internal/generated"
	reportpersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage_status_report/persistence"
)

func runStatusReportMongoContainer(
	ctx context.Context,
) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", recovered)
		}
	}()
	testinfra.ConfigureLocalContainerRuntime()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

type statusReportHomepageGate struct{}

func (statusReportHomepageGate) FindHomepageStatus(
	_ context.Context,
	_ string,
) (string, bool, error) {
	return "published", true, nil
}

func reportContext(key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "status-report-packet-integration",
		RequestID:      "request-" + key,
		TraceID:        "trace-" + key,
		IdempotencyKey: key,
	})
}

func TestHomepageStatusReportMongoPacket(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()
	container, err := runStatusReportMongoContainer(ctx)
	if err != nil {
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	defer func() { _ = client.Disconnect(context.Background()) }()

	store := reportpersistence.NewMongoStore(client.Database("entity_status_report_packet_it"), true)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure status report indexes: %v", err)
	}
	facade, err := reportapp.NewFacade(reportapp.DataPorts{
		Aggregates: store,
		Receipts:   store,
		Homepages:  statusReportHomepageGate{},
		Queue:      store,
	})
	if err != nil {
		t.Fatalf("new status report facade: %v", err)
	}
	now := time.Date(2026, 7, 20, 4, 0, 0, 0, time.UTC)
	tick := 0
	facade.SetClock(func() time.Time {
		tick++
		return now.Add(time.Duration(tick) * time.Second)
	})
	nextID := 0
	facade.SetIDGenerator(func() string {
		nextID++
		return fmt.Sprintf("report-mongo-%d", nextID)
	})
	command := reportapp.CreateCommand{
		HomepageID:     "hp-report-mongo",
		ActorPersonaID: "persona-report-mongo",
		Reason:         reportmodel.ReasonOffline,
		Description:    "confirmed closed",
		EvidenceURLs:   []string{"https://assets.test/offline-proof"},
	}
	created, err := facade.Create(reportContext("report-create"), command)
	if err != nil {
		t.Fatalf("create status report through transaction: %v", err)
	}
	replayed, err := facade.Create(reportContext("report-create"), command)
	if err != nil || replayed.ReportID != created.ReportID {
		t.Fatalf("status report receipt replay mismatch: %+v err=%v", replayed, err)
	}
	changed := command
	changed.Description = "different digest"
	if _, err := facade.Create(reportContext("report-create"), changed); !reportCode(
		err, generated.ErrIdempotencyConflict,
	) {
		t.Fatalf("status report digest conflict expected: %v", err)
	}

	duplicate := newStatusReportAggregate(
		t, "report-mongo-duplicate", command, now.Add(10*time.Second),
	)
	if _, err := store.Commit(ctx, reportCommit(
		duplicate, 0, "report-db-duplicate", "report-db-duplicate-event",
	)); !reportCode(err, generated.ErrInvalidArgument) {
		t.Fatalf("partial pending status report unique index must reject duplicate: %v", err)
	}
	dismissed, err := facade.Review(reportContext("report-review"), reportapp.ReviewCommand{
		HomepageID:     created.HomepageID,
		ReportID:       created.ReportID,
		ActorAccountID: "account-report-reviewer",
		TargetStatus:   reportmodel.StatusDismissed,
	})
	if err != nil || dismissed.Version != 2 {
		t.Fatalf("dismiss report through transaction: %+v err=%v", dismissed, err)
	}
	noop, err := facade.Review(reportContext("report-review-noop"), reportapp.ReviewCommand{
		HomepageID:     created.HomepageID,
		ReportID:       created.ReportID,
		ActorAccountID: "account-report-reviewer-2",
		TargetStatus:   reportmodel.StatusDismissed,
	})
	if err != nil || noop.Version != dismissed.Version {
		t.Fatalf("same report terminal target must be no-op: %+v err=%v", noop, err)
	}

	second, err := facade.Create(reportContext("report-create-second"), command)
	if err != nil {
		t.Fatalf("partial unique index must release after terminal review: %v", err)
	}
	firstClone, found, err := store.Load(ctx, second.ReportID)
	if err != nil || !found {
		t.Fatalf("load first report CAS clone: found=%v err=%v", found, err)
	}
	staleClone, found, err := store.Load(ctx, second.ReportID)
	if err != nil || !found {
		t.Fatalf("load stale report CAS clone: found=%v err=%v", found, err)
	}
	for _, aggregate := range []*reportmodel.HomepageStatusReport{firstClone, staleClone} {
		if err := aggregate.Review(reportmodel.ReviewParams{
			ReviewerAccountID: "account-cas",
			TargetStatus:      reportmodel.StatusConfirmedOffline,
			Now:               now.Add(20 * time.Second),
		}); err != nil {
			t.Fatalf("prepare report CAS review: %v", err)
		}
	}
	if _, err := store.Commit(ctx, reportCommit(
		firstClone, 1, "report-cas-winner", "report-cas-winner-event",
	)); err != nil {
		t.Fatalf("status report CAS winner commit: %v", err)
	}
	if _, err := store.Commit(ctx, reportCommit(
		staleClone, 1, "report-cas-stale", "report-cas-stale-event",
	)); !reportCode(err, generated.ErrVersionConflict) {
		t.Fatalf("stale status report CAS commit must conflict: %v", err)
	}

	events, err := store.ReadAfter(ctx, "", 100)
	if err != nil || len(events) != 4 {
		t.Fatalf("status report outbox count mismatch: count=%d err=%v", len(events), err)
	}
	for _, event := range events {
		payload := string(event.Payload)
		if !strings.Contains(payload, `"reportId"`) || strings.Contains(payload, `"_id"`) {
			t.Fatalf("status report outbox must use canonical reportId: %s", payload)
		}
	}
	lastEventID := events[len(events)-1].EventID
	if err := store.SaveCheckpoint(ctx, "status-report-projection-test", lastEventID); err != nil {
		t.Fatalf("save status report checkpoint: %v", err)
	}
	checkpoint, err := store.LoadCheckpoint(ctx, "status-report-projection-test")
	if err != nil || checkpoint != lastEventID {
		t.Fatalf("status report checkpoint mismatch: %q err=%v", checkpoint, err)
	}
	after, err := store.ReadAfter(ctx, lastEventID, 100)
	if err != nil || len(after) != 0 {
		t.Fatalf("status report outbox checkpoint replay mismatch: count=%d err=%v", len(after), err)
	}
}

func newStatusReportAggregate(
	t *testing.T,
	id string,
	command reportapp.CreateCommand,
	now time.Time,
) *reportmodel.HomepageStatusReport {
	t.Helper()
	aggregate, err := reportmodel.Create(reportmodel.CreateParams{
		ID:                id,
		HomepageID:        command.HomepageID,
		ReporterPersonaID: command.ActorPersonaID,
		Reason:            command.Reason,
		Description:       command.Description,
		EvidenceURLs:      command.EvidenceURLs,
		Now:               now,
	})
	if err != nil {
		t.Fatalf("create status report aggregate: %v", err)
	}
	return aggregate
}

func reportCommit(
	aggregate *reportmodel.HomepageStatusReport,
	expectedVersion int64,
	key string,
	eventID string,
) reportports.Commit {
	snapshot := aggregate.Snapshot()
	payload := []byte(fmt.Sprintf(`{"reportId":%q}`, snapshot.ID))
	return reportports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   key,
		CommandName:      "IntegrationStatusReportCommit",
		CommandDigest:    key + "-digest",
		ReceiptExpiresAt: time.Now().UTC().Add(24 * time.Hour),
		Events: []reportports.OutboxEvent{{
			EventID:          eventID,
			EventType:        "HomepageStatusReportReviewed",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       snapshot.UpdatedAt,
		}},
	}
}

func reportCode(err error, sentinel error) bool {
	if err == nil || sentinel == nil {
		return false
	}
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == sentinel.Error()
}
