// Command search-backfill rebuilds the unified search index from the live entity
// store (cold start / reconcile for entity.search_index_worker).
//
// It ensures the shared ES/OpenSearch index exists, then lists every published
// homepage, projects it through the single shared projection
// (application.ProjectHomepageToSearchDocument) and bulk-upserts it. Run it after
// a fresh import or to repair drift; the write-time projector keeps the index in
// sync afterwards.
//
// ES endpoints/credentials come from the shared SEARCH_ES_* env (deploy secrets),
// the same way entity-service / search-service receive them. Flags only cover
// mongo connection + local overrides; no cluster URL is hardcoded.
//
// Usage:
//
//	SEARCH_ES_ENDPOINTS=https://es:9200 SEARCH_ES_USERNAME=elastic SEARCH_ES_PASSWORD=... \
//	  go run ./services/entity-service/cmd/search-backfill \
//	  --mongo-uri mongodb://localhost:27017 --entity-db quwoquan_entity --env gamma
package main

import (
	"context"
	"flag"
	"log"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/internal/application"
	"quwoquan_service/services/entity-service/internal/infrastructure/persistence"
	"quwoquan_service/services/entity-service/internal/infrastructure/searchindex"
)

func main() {
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	entityDB := flag.String("entity-db", "quwoquan_entity", "entity database name")
	stateColl := flag.String("state-collection", "homepage_state", "homepage state collection name")
	esIndex := flag.String("es-index", "", "ES index name (default: quwoquan_objects)")
	esEndpoints := flag.String("es-endpoints", "", "comma-separated ES endpoints (overrides SEARCH_ES_ENDPOINTS)")
	batchSize := flag.Int("batch-size", 0, "bulk batch size (0 = default)")
	env := flag.String("env", "", "environment label (for logging)")
	flag.Parse()

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
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("[search-backfill] mongo connect: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = client.Disconnect(shutdownCtx)
	}()

	store := persistence.NewMongoHomepageStateStore(client.Database(*entityDB).Collection(*stateColl))
	// The homepage service hydrates the full state from the store on construction,
	// so it is the live HomepageLister for backfill.
	service := application.NewHomepageServiceWithStore(ctx, store)

	built, err := searchindex.Build(esCfg)
	if err != nil {
		log.Fatalf("[search-backfill] es client build: %v", err)
	}
	if built.Client == nil {
		log.Fatalf("[search-backfill] es disabled after config resolution")
	}

	report, err := searchindex.Backfill(ctx, built.Client, service, *batchSize)
	if err != nil {
		log.Fatalf("[search-backfill] backfill failed (indexed=%d batches=%d): %v", report.IndexedHomepages, report.BatchesPushed, err)
	}
	log.Printf("[search-backfill] OK env=%s index=%s total=%d indexed=%d skipped=%d batches=%d",
		*env, built.Client.IndexName(), report.TotalHomepages, report.IndexedHomepages, report.SkippedHomepages, report.BatchesPushed)
}
