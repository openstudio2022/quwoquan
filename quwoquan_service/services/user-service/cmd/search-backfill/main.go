// Command search-backfill rebuilds the unified search index from the live user
// profile store (cold start / reconcile for user.search_index_worker).
//
// It ensures the shared ES/OpenSearch index exists, then pages through every
// active user profile by ascending user_id, projects it through the single shared
// projection (application.ProjectUserProfileToSearchDocument) and bulk-upserts it.
// Run it after a fresh import or to repair drift; the write-time projector keeps
// the index in sync afterwards.
//
// ES endpoints/credentials come from the shared SEARCH_ES_* env (deploy secrets),
// the same way user-service / search-service receive them. The Postgres DSN comes
// from --postgres-dsn or POSTGRES_DSN; no cluster URL is hardcoded.
//
// Usage:
//
//	SEARCH_ES_ENDPOINTS=https://es:9200 SEARCH_ES_USERNAME=elastic SEARCH_ES_PASSWORD=... \
//	  POSTGRES_DSN=postgres://user:pass@localhost:5432/quwoquan_user \
//	  go run ./services/user-service/cmd/search-backfill --env gamma
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/searchindex"
)

func main() {
	postgresDSN := flag.String("postgres-dsn", "", "postgres DSN (overrides POSTGRES_DSN)")
	esIndex := flag.String("es-index", "", "ES index name (default: quwoquan_objects)")
	esEndpoints := flag.String("es-endpoints", "", "comma-separated ES endpoints (overrides SEARCH_ES_ENDPOINTS)")
	batchSize := flag.Int("batch-size", 0, "bulk batch / page size (0 = default)")
	env := flag.String("env", "", "environment label (for logging)")
	flag.Parse()

	dsn := strings.TrimSpace(*postgresDSN)
	if dsn == "" {
		dsn = strings.TrimSpace(os.Getenv("POSTGRES_DSN"))
	}
	if dsn == "" {
		log.Fatalf("[search-backfill] no postgres DSN: set POSTGRES_DSN or --postgres-dsn")
	}

	// Build ES config from the shared SEARCH_ES_* env, then apply explicit flag
	// overrides so local/manual reconcile runs work without mutating env.
	esCfg := searchindex.ESConfig{Index: strings.TrimSpace(*esIndex)}
	searchindex.ApplyESEnvOverrides(&esCfg)
	if eps := strings.TrimSpace(*esEndpoints); eps != "" {
		parts := strings.Split(eps, ",")
		out := make([]string, 0, len(parts))
		for _, p := range parts {
			if p = strings.TrimSpace(p); p != "" {
				out = append(out, p)
			}
		}
		esCfg.Endpoints = out
		esCfg.Enabled = true
	}
	if len(esCfg.Endpoints) == 0 {
		log.Fatalf("[search-backfill] no ES endpoints: set SEARCH_ES_ENDPOINTS or --es-endpoints")
	}
	esCfg.Enabled = true

	ctx := context.Background()
	pgPool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		log.Fatalf("[search-backfill] postgres connect: %v", err)
	}
	defer pgPool.Close()
	if err := pgPool.Ping(ctx); err != nil {
		log.Fatalf("[search-backfill] postgres ping: %v", err)
	}

	store := persistence.NewPgProfileStore(pgPool)

	built, err := searchindex.Build(esCfg, store)
	if err != nil {
		log.Fatalf("[search-backfill] es client build: %v", err)
	}
	if built.Client == nil {
		log.Fatalf("[search-backfill] es disabled after config resolution")
	}

	report, err := searchindex.Backfill(ctx, built.Client, store, *batchSize)
	if err != nil {
		log.Fatalf("[search-backfill] backfill failed (indexed=%d batches=%d): %v", report.IndexedProfiles, report.BatchesPushed, err)
	}
	log.Printf("[search-backfill] OK env=%s index=%s total=%d indexed=%d deleted=%d batches=%d",
		*env, built.Client.IndexName(), report.TotalProfiles, report.IndexedProfiles, report.DeletedProfiles, report.BatchesPushed)
}
