// Command search-backfill rebuilds the unified search index from the live content
// store (cold start / reconcile for content.search_index_worker).
//
// It ensures the shared ES/OpenSearch index exists, then lists every published +
// public post, projects it through the single shared projection
// (searchprojection.ProjectPostToSearchDocument) and bulk-upserts it. Run it after a
// fresh import or to repair drift; the write-time projector keeps the index in
// sync afterwards.
//
// ES endpoints/credentials come from the shared SEARCH_ES_* env (deploy secrets),
// the same way content-service / search-service receive them. Flags only cover
// mongo connection + local overrides; no cluster URL is hardcoded.
//
// Usage:
//
//	SEARCH_ES_ENDPOINTS=https://es:9200 SEARCH_ES_USERNAME=elastic SEARCH_ES_PASSWORD=... \
//	  go run ./services/content-service/cmd/search-backfill \
//	  --mongo-uri mongodb://localhost:27017 --posts-db quwoquan_content --env gamma
package main

import (
	"context"
	"flag"
	"log"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
)

func main() {
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	postsDB := flag.String("posts-db", "quwoquan_content", "posts database name")
	postsColl := flag.String("posts-collection", "posts", "posts collection name")
	esIndex := flag.String("es-index", "", "ES index name (default: quwoquan_objects)")
	esEndpoints := flag.String("es-endpoints", "", "comma-separated ES endpoints (overrides SEARCH_ES_ENDPOINTS)")
	batchSize := flag.Int("batch-size", 0, "bulk batch size (0 = default)")
	requestTimeout := flag.Duration("request-timeout", 0, "per-request ES timeout for this reconcile run (0 = configured/default)")
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
	if *requestTimeout > 0 {
		esCfg.RequestTimeoutMs = int(requestTimeout.Milliseconds())
	}

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

	store := persistence.NewMongoPostStore(client.Database(*postsDB).Collection(*postsColl))

	built, err := searchindex.Build(esCfg, store)
	if err != nil {
		log.Fatalf("[search-backfill] es client build: %v", err)
	}
	if built.Client == nil {
		log.Fatalf("[search-backfill] es disabled after config resolution")
	}

	report, err := searchindex.Backfill(ctx, built.Client, store, *batchSize)
	if err != nil {
		log.Fatalf("[search-backfill] backfill failed (indexed=%d batches=%d): %v", report.IndexedPosts, report.BatchesPushed, err)
	}
	log.Printf("[search-backfill] OK env=%s index=%s total=%d indexed=%d deleted=%d batches=%d",
		*env, built.Client.IndexName(), report.TotalPosts, report.IndexedPosts, report.DeletedPosts, report.BatchesPushed)

	// Rebuild first-party place snapshots (location.place) from the same posts
	// into the same shared index (R-S05e): aggregate free-text locations not yet
	// bound to a canonical entity, dedup by canonical id, materialize + index.
	placeStore := placeindex.NewMongoPlaceStore(client.Database(*postsDB).Collection(placeindex.PlaceSnapshotCollection), nil)
	placeReport, err := placeindex.Backfill(ctx, built.Client, store, placeStore, *batchSize)
	if err != nil {
		log.Fatalf("[search-backfill] place backfill failed (places=%d batches=%d): %v", placeReport.IndexedPlaces, placeReport.BatchesPushed, err)
	}
	log.Printf("[search-backfill] places OK env=%s index=%s posts=%d referenced=%d indexed=%d deleted=%d batches=%d",
		*env, built.Client.IndexName(), placeReport.TotalPosts, placeReport.ReferencedPosts, placeReport.IndexedPlaces, placeReport.DeletedPlaces, placeReport.BatchesPushed)
}
