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
	claimapp "quwoquan_service/services/entity-service/internal/application/homepage_claim_request"
	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	"quwoquan_service/services/entity-service/internal/generated"
	claimpersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage_claim_request/persistence"
)

func runClaimMongoContainer(
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

type claimHomepageGate struct{}

func (claimHomepageGate) FindHomepageState(
	_ context.Context,
	_ string,
) (claimapp.HomepageState, bool, error) {
	return claimapp.HomepageState{Status: "published", ClaimStatus: "unclaimed"}, true, nil
}

func claimContext(key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "claim-packet-integration",
		RequestID:      "request-" + key,
		TraceID:        "trace-" + key,
		IdempotencyKey: key,
	})
}

func TestHomepageClaimRequestMongoPacket(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()
	container, err := runClaimMongoContainer(ctx)
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

	store := claimpersistence.NewMongoStore(client.Database("entity_claim_packet_it"), true)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure claim indexes: %v", err)
	}
	facade, err := claimapp.NewFacade(claimapp.DataPorts{
		Aggregates: store,
		Receipts:   store,
		Homepages:  claimHomepageGate{},
		Queue:      store,
	})
	if err != nil {
		t.Fatalf("new claim facade: %v", err)
	}
	now := time.Date(2026, 7, 20, 3, 0, 0, 0, time.UTC)
	tick := 0
	facade.SetClock(func() time.Time {
		tick++
		return now.Add(time.Duration(tick) * time.Second)
	})
	nextID := 0
	facade.SetIDGenerator(func() string {
		nextID++
		return fmt.Sprintf("claim-mongo-%d", nextID)
	})
	command := claimapp.CreateCommand{
		HomepageID:           "hp-claim-mongo",
		ActorPersonaID:       "persona-claim-mongo",
		ClaimTier:            claimmodel.ClaimTierVerified,
		BusinessLicenseURL:   "https://assets.test/license",
		ContactPhone:         "13800000000",
		IdentityCardFrontURL: "https://assets.test/id-front",
		IdentityCardBackURL:  "https://assets.test/id-back",
	}
	created, err := facade.Create(claimContext("claim-create"), command)
	if err != nil {
		t.Fatalf("create claim through transaction: %v", err)
	}
	replayed, err := facade.Create(claimContext("claim-create"), command)
	if err != nil || replayed.ClaimRequestID != created.ClaimRequestID {
		t.Fatalf("claim receipt replay mismatch: %+v err=%v", replayed, err)
	}
	changed := command
	changed.Note = "different digest"
	if _, err := facade.Create(claimContext("claim-create"), changed); !claimCode(
		err, generated.ErrIdempotencyConflict,
	) {
		t.Fatalf("claim digest conflict expected: %v", err)
	}

	duplicate := newClaimAggregate(t, "claim-mongo-duplicate", command, now.Add(10*time.Second))
	if _, err := store.Commit(ctx, claimCommit(
		duplicate, 0, "claim-db-duplicate", "claim-db-duplicate-event",
	)); !claimCode(err, generated.ErrDuplicatePendingClaim) {
		t.Fatalf("partial pending claim unique index must reject duplicate: %v", err)
	}
	approved, err := facade.Review(claimContext("claim-review"), claimapp.ReviewCommand{
		HomepageID:     created.HomepageID,
		ClaimRequestID: created.ClaimRequestID,
		ActorAccountID: "account-claim-reviewer",
		TargetStatus:   claimmodel.StatusApproved,
	})
	if err != nil || approved.Version != 2 {
		t.Fatalf("approve claim through transaction: %+v err=%v", approved, err)
	}
	noop, err := facade.Review(claimContext("claim-review-noop"), claimapp.ReviewCommand{
		HomepageID:     created.HomepageID,
		ClaimRequestID: created.ClaimRequestID,
		ActorAccountID: "account-claim-reviewer-2",
		TargetStatus:   claimmodel.StatusApproved,
	})
	if err != nil || noop.Version != approved.Version {
		t.Fatalf("same claim terminal target must be no-op: %+v err=%v", noop, err)
	}

	second, err := facade.Create(claimContext("claim-create-second"), command)
	if err != nil {
		t.Fatalf("partial unique index must release after terminal review: %v", err)
	}
	firstClone, found, err := store.Load(ctx, second.ClaimRequestID)
	if err != nil || !found {
		t.Fatalf("load first claim CAS clone: found=%v err=%v", found, err)
	}
	staleClone, found, err := store.Load(ctx, second.ClaimRequestID)
	if err != nil || !found {
		t.Fatalf("load stale claim CAS clone: found=%v err=%v", found, err)
	}
	for _, aggregate := range []*claimmodel.HomepageClaimRequest{firstClone, staleClone} {
		if err := aggregate.Review(claimmodel.ReviewParams{
			ReviewerAccountID: "account-cas",
			TargetStatus:      claimmodel.StatusRejected,
			Now:               now.Add(20 * time.Second),
		}); err != nil {
			t.Fatalf("prepare claim CAS review: %v", err)
		}
	}
	if _, err := store.Commit(ctx, claimCommit(
		firstClone, 1, "claim-cas-winner", "claim-cas-winner-event",
	)); err != nil {
		t.Fatalf("claim CAS winner commit: %v", err)
	}
	if _, err := store.Commit(ctx, claimCommit(
		staleClone, 1, "claim-cas-stale", "claim-cas-stale-event",
	)); !claimCode(err, generated.ErrVersionConflict) {
		t.Fatalf("stale claim CAS commit must conflict: %v", err)
	}

	events, err := store.ReadAfter(ctx, "", 100)
	if err != nil || len(events) != 4 {
		t.Fatalf("claim outbox count mismatch: count=%d err=%v", len(events), err)
	}
	for _, event := range events {
		payload := string(event.Payload)
		if !strings.Contains(payload, `"claimRequestId"`) || strings.Contains(payload, `"_id"`) {
			t.Fatalf("claim outbox must use canonical claimRequestId: %s", payload)
		}
	}
	lastEventID := events[len(events)-1].EventID
	if err := store.SaveCheckpoint(ctx, "claim-projection-test", lastEventID); err != nil {
		t.Fatalf("save claim checkpoint: %v", err)
	}
	checkpoint, err := store.LoadCheckpoint(ctx, "claim-projection-test")
	if err != nil || checkpoint != lastEventID {
		t.Fatalf("claim checkpoint mismatch: %q err=%v", checkpoint, err)
	}
	after, err := store.ReadAfter(ctx, lastEventID, 100)
	if err != nil || len(after) != 0 {
		t.Fatalf("claim outbox checkpoint replay mismatch: count=%d err=%v", len(after), err)
	}
}

func newClaimAggregate(
	t *testing.T,
	id string,
	command claimapp.CreateCommand,
	now time.Time,
) *claimmodel.HomepageClaimRequest {
	t.Helper()
	aggregate, err := claimmodel.Create(claimmodel.CreateParams{
		ID:                   id,
		HomepageID:           command.HomepageID,
		RequesterPersonaID:   command.ActorPersonaID,
		ClaimTier:            command.ClaimTier,
		BusinessLicenseURL:   command.BusinessLicenseURL,
		ContactPhone:         command.ContactPhone,
		IdentityCardFrontURL: command.IdentityCardFrontURL,
		IdentityCardBackURL:  command.IdentityCardBackURL,
		Now:                  now,
	})
	if err != nil {
		t.Fatalf("create claim aggregate: %v", err)
	}
	return aggregate
}

func claimCommit(
	aggregate *claimmodel.HomepageClaimRequest,
	expectedVersion int64,
	key string,
	eventID string,
) claimports.Commit {
	snapshot := aggregate.Snapshot()
	payload := []byte(fmt.Sprintf(`{"claimRequestId":%q}`, snapshot.ID))
	return claimports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   key,
		CommandName:      "IntegrationClaimCommit",
		CommandDigest:    key + "-digest",
		ReceiptExpiresAt: time.Now().UTC().Add(24 * time.Hour),
		Events: []claimports.OutboxEvent{{
			EventID:          eventID,
			EventType:        "HomepageClaimReviewed",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       snapshot.UpdatedAt,
		}},
	}
}

func claimCode(err error, sentinel error) bool {
	if err == nil || sentinel == nil {
		return false
	}
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == sentinel.Error()
}
