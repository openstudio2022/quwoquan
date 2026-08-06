package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	contactmodel "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	contactports "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/ports"
	contactpersistence "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestContactDiscoveryRecordPostgresPersistsOnlyHashesAndExpires(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "contact-owner", "contact-persona"); err != nil {
			t.Fatal(err)
		}
		store := contactpersistence.NewPgContactDiscoveryStore(pool)
		hashedPhone := fmt.Sprintf(
			"sha256:%x",
			sha256.Sum256([]byte("+8613800000001")),
		)
		record := &contactmodel.ContactDiscoveryRecord{
			ID: "contact-discovery-1", OwnerAccountID: "contact-owner",
			HashedPhones: []string{hashedPhone}, Status: "pending",
			ExpireAt: time.Now().UTC().Add(time.Hour), CreatedAt: time.Now().UTC(),
		}
		command := contactports.CommandIdentity{
			Operation:      "InitiateContactDiscovery",
			OwnerAccountID: record.OwnerAccountID,
			IdempotencyKey: "contact-discovery-replay-1",
			CommandDigest:  testCommandDigest("initiate", hashedPhone),
		}
		created, inserted, err := store.CreateIdempotent(ctx, record, 5, command)
		if err != nil || !inserted || created.ID != record.ID {
			t.Fatalf("create idempotent: inserted=%v value=%+v err=%v", inserted, created, err)
		}
		completed, transitioned, err := store.CompleteIdempotent(
			ctx, record.ID, []string{"matched-persona"}, command,
		)
		if err != nil || !transitioned || completed.Status != "completed" {
			t.Fatalf("complete idempotent: transitioned=%v value=%+v err=%v", transitioned, completed, err)
		}
		stored, err := store.FindByID(ctx, record.ID)
		if err != nil || stored.Status != "completed" || stored.MatchCount != 1 || len(stored.HashedPhones) != 1 {
			t.Fatalf("ContactDiscoveryRecord drift: value=%+v err=%v", stored, err)
		}

		replayed, inserted, err := store.CreateIdempotent(
			ctx,
			&contactmodel.ContactDiscoveryRecord{
				ID:             "must-not-be-created",
				OwnerAccountID: record.OwnerAccountID,
				HashedPhones:   []string{"different-candidate"},
				Status:         "pending",
				ExpireAt:       time.Now().UTC().Add(time.Hour),
			},
			5,
			command,
		)
		if err != nil || inserted || replayed.ID != record.ID ||
			replayed.Status != "completed" || len(replayed.HashedPhones) != 1 ||
			replayed.HashedPhones[0] != hashedPhone {
			t.Fatalf("replay must return first private snapshot: inserted=%v value=%+v err=%v", inserted, replayed, err)
		}
		conflict := command
		conflict.CommandDigest = testCommandDigest("initiate", "changed-payload")
		if _, _, err := store.CreateIdempotent(ctx, record, 5, conflict); !errors.Is(err, contactports.ErrIdempotencyConflict) {
			t.Fatalf("same key with changed payload must conflict, got %v", err)
		}
		var aggregateCount, receiptCount int
		if err := pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM contact_discovery_records WHERE owner_account_id=$1`,
			record.OwnerAccountID,
		).Scan(&aggregateCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM contact_discovery_command_receipts WHERE owner_account_id=$1`,
			record.OwnerAccountID,
		).Scan(&receiptCount); err != nil {
			t.Fatal(err)
		}
		if aggregateCount != 1 || receiptCount != 1 {
			t.Fatalf("replay duplicated state: aggregates=%d receipts=%d", aggregateCount, receiptCount)
		}

		dismiss := contactports.CommandIdentity{
			Operation:      "DismissContactDiscovery",
			OwnerAccountID: record.OwnerAccountID,
			IdempotencyKey: "contact-discovery-dismiss-1",
			CommandDigest:  testCommandDigest("dismiss", record.ID),
		}
		if err := store.DismissIdempotent(ctx, record.ID, dismiss); err != nil {
			t.Fatalf("dismiss command: %v", err)
		}
		if err := store.DismissIdempotent(ctx, record.ID, dismiss); err != nil {
			t.Fatalf("dismiss replay: %v", err)
		}
		wrongOwner := dismiss
		wrongOwner.OwnerAccountID = "another-owner"
		wrongOwner.IdempotencyKey = "contact-discovery-dismiss-wrong-owner"
		wrongOwner.CommandDigest = testCommandDigest("dismiss", "another-owner", record.ID)
		if err := store.DismissIdempotent(ctx, record.ID, wrongOwner); !errors.Is(err, contactports.ErrNotFound) {
			t.Fatalf("another owner must not dismiss record, got %v", err)
		}
		stored, err = store.FindByID(ctx, record.ID)
		if err != nil || stored.Status != "dismissed" {
			t.Fatalf("dismissed state drift: value=%+v err=%v", stored, err)
		}
	})
}

func testCommandDigest(parts ...string) string {
	digest := sha256.Sum256([]byte(fmt.Sprint(parts)))
	return hex.EncodeToString(digest[:])
}
