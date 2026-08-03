// Command search-backfill rebuilds the unified search index from the live entity
// store (cold start / reconcile for entity.search_index_worker).
//
// It ensures the shared ES/OpenSearch index exists, then lists every published
// homepage, projects it through HomepageSearchItemView's one typed projector and
// records its monotonic checkpoint. Run it after
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

	entitycomposition "quwoquan_service/services/entity-service/cmd/internal/composition"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	searchitempersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/infrastructure/persistence"
	searchitemindex "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/infrastructure/searchindex"
)

func main() {
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	entityDB := flag.String("entity-db", "quwoquan_entity", "entity database name")
	esIndex := flag.String("es-index", "", "ES index name (default: quwoquan_objects)")
	esEndpoints := flag.String("es-endpoints", "", "comma-separated ES endpoints (overrides SEARCH_ES_ENDPOINTS)")
	batchSize := flag.Int("batch-size", 0, "bulk batch size (0 = default)")
	env := flag.String("env", "", "environment label (for logging)")
	flag.Parse()

	// Build ES config from the shared SEARCH_ES_* env, then apply explicit flag
	// overrides so local/manual reconcile runs work without mutating env.
	esCfg := searchitemindex.ESConfig{Index: strings.TrimSpace(*esIndex)}
	searchitemindex.ApplyESEnvOverrides(&esCfg)
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

	database := client.Database(*entityDB)
	store := homepagepersistence.NewMongoHomepageStore(database, false)
	if err := store.EnsureIndexes(ctx); err != nil {
		log.Fatalf("[search-backfill] ensure homepage indexes: %v", err)
	}
	// Backfill 通过 HomepageQueryFacade cursor 扫描权威 homepages 集合。
	service := application.NewHomepageServiceWithStore(ctx, store)

	built, err := searchitemindex.Build(esCfg)
	if err != nil {
		log.Fatalf("[search-backfill] es client build: %v", err)
	}
	if built.Client == nil {
		log.Fatalf("[search-backfill] es disabled after config resolution")
	}

	index := searchitempersistence.NewESIndex(built.Indexer, database)
	if err := index.EnsureIndexes(ctx); err != nil {
		log.Fatalf("[search-backfill] ensure checkpoint indexes: %v", err)
	}
	projection := entitycomposition.NewHomepageSearchItemProjection(index)
	limit := *batchSize
	if limit <= 0 {
		limit = 500
	}
	total, indexed, deleted := 0, 0, 0
	cursor := ""
	for {
		homepages, nextCursor, scanErr := service.ScanHomepagesForIndex(ctx, cursor, limit)
		if scanErr != nil {
			log.Fatalf("[search-backfill] scan failed after total=%d: %v", total, scanErr)
		}
		for index := range homepages {
			homepage := homepages[index]
			eventType := application.ProjectorEventHomepageUpserted
			if !application.HomepageSearchEligible(homepage) {
				eventType = application.ProjectorEventHomepageRemoved
			}
			if projectErr := projection.Project(ctx, application.ProjectorEvent{
				Type: eventType, HomepageID: homepage.ID, SourceVersion: homepage.Version,
				Homepage: &homepage,
			}); projectErr != nil {
				log.Fatalf("[search-backfill] project homepageId=%s: %v", homepage.ID, projectErr)
			}
			total++
			if eventType == application.ProjectorEventHomepageRemoved {
				deleted++
			} else {
				indexed++
			}
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	log.Printf("[search-backfill] OK env=%s index=%s total=%d indexed=%d deleted=%d",
		*env, built.Client.IndexName(), total, indexed, deleted)
}
