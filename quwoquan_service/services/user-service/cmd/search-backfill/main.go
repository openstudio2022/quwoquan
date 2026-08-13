// Command search-backfill re-enqueues every user profile's public snapshot
// into the User-owned search projection outbox (cold start / index-rebuild
// reconcile for user.profile documents).
//
// User never writes the search provider directly
// (canonical-search-contract REQ-003): the reconcile replays the same
// single-track UserProfileSearchProjectionRequested outbox events the write
// path emits, and the existing outbox relay + SearchIndexView consumer carry
// them into the unified index (idempotent by eventId, monotonic by
// profileVersion).
//
// Usage:
//
//	go run ./services/user-service/cmd/search-backfill \
//	  --pg-uri postgres://user:pass@localhost:5432/quwoquan_user --env gamma
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

func main() {
	pgURI := flag.String("pg-uri", "", "postgres connection uri (overrides USER_PG_URI)")
	batchSize := flag.Int("batch-size", 500, "profiles per page")
	env := flag.String("env", "", "environment label (for logging)")
	flag.Parse()

	uri := strings.TrimSpace(*pgURI)
	if uri == "" {
		uri = strings.TrimSpace(os.Getenv("USER_PG_URI"))
	}
	if uri == "" {
		log.Fatal("[user-search-backfill] no postgres uri: set USER_PG_URI or --pg-uri")
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, uri)
	if err != nil {
		log.Fatalf("[user-search-backfill] postgres connect: %v", err)
	}
	defer pool.Close()

	store := persistence.NewPgProfileStore(pool)
	afterUserID := ""
	total, enqueued, failed := 0, 0, 0
	startedAt := time.Now()
	for {
		profiles, err := store.ListProfilesForIndex(ctx, afterUserID, *batchSize)
		if err != nil {
			log.Fatalf("[user-search-backfill] list profiles after %q: %v", afterUserID, err)
		}
		if len(profiles) == 0 {
			break
		}
		for _, profile := range profiles {
			total++
			if err := store.EnqueueUserProfileSearchBackfill(ctx, profile, time.Now().UTC()); err != nil {
				failed++
				log.Printf("[user-search-backfill] enqueue %s failed: %v", profile.UserID, err)
				continue
			}
			enqueued++
		}
		afterUserID = profiles[len(profiles)-1].UserID
	}
	log.Printf(
		"[user-search-backfill] env=%s total=%d enqueued=%d failed=%d elapsed=%s (outbox relay delivers to search-service)",
		*env, total, enqueued, failed, time.Since(startedAt).Round(time.Millisecond),
	)
	if failed > 0 {
		os.Exit(1)
	}
}
