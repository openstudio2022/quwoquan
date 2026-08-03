package api_integration

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingports "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
	greetingpersistence "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestGreetingRequestPostgresStateReceiptAndOutboxAreAtomic(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := greetingpersistence.NewPgGreetingStore(pool)
		now := time.Now().UTC()
		greeting := &greetingmodel.GreetingRequest{
			ID: "greeting-1", RequesterPersonaID: "requester", TargetPersonaID: "target",
			RequestMessage: "你好", Status: greetingmodel.GreetingStatusPending, Source: "homepage", CreatedAt: now, UpdatedAt: now,
		}
		if err := store.CommitCommand(ctx, greetingports.GreetingCommit{
			Greeting: greeting, Insert: true, ActorPersonaID: greeting.RequesterPersonaID,
			IdempotencyKey: "greeting-send-key", Operation: "SendGreetingRequest",
			EventID: "greeting-event-1", EventName: "GreetingRequestSent", EventPayload: map[string]any{"id": greeting.ID}, OccurredAt: now,
		}); err != nil {
			t.Fatal(err)
		}
		replayed, found, err := store.LoadCommandReceipt(ctx, greeting.RequesterPersonaID, "greeting-send-key", "SendGreetingRequest")
		if err != nil || !found || replayed.ID != greeting.ID {
			t.Fatalf("GreetingRequest receipt drift: value=%+v found=%v err=%v", replayed, found, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM greeting_request_outbox WHERE aggregate_id=$1`, greeting.ID).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("GreetingRequest outbox=%d err=%v", outboxCount, err)
		}
	})
}
