// Command search-reindex drives the zero-downtime rebuild of the unified
// search index (search-storage-topology REQ-006).
//
// The read alias (quwoquan_objects) and write alias (quwoquan_objects-write)
// point at one versioned physical index (quwoquan_objects-vN). Analyzer or
// breaking-mapping changes cannot mutate an index in place, so the rebuild
// sequence is:
//
//  1. --begin    create quwoquan_objects-v(N+1) with the current schema and
//     atomically move the WRITE alias onto it. Every incremental
//     owner projection now lands in the new index — the rebuild
//     window cannot lose writes.
//  2. run every owner cold backfill against the write alias:
//     content-service/circle-service/entity-service/user-service
//     cmd/search-backfill.
//  3. --promote  compare doc counts, then atomically move the READ alias onto
//     the new index.
//  4. --cleanup  delete the retired physical index once no alias references it.
//
// ES endpoints/credentials come from the shared SEARCH_ES_* env (deploy
// secrets); flags only provide local overrides.
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"strings"
	"time"

	"quwoquan_service/runtime/search/es"
)

func main() {
	begin := flag.Bool("begin", false, "create the next physical index and move the write alias onto it")
	promote := flag.String("promote", "", "physical index to promote the read alias onto")
	cleanup := flag.String("cleanup", "", "retired physical index to delete (must be unreferenced)")
	status := flag.Bool("status", false, "print alias -> physical index bindings and doc counts")
	esIndex := flag.String("es-index", "", "read alias name (default: quwoquan_objects)")
	esEndpoints := flag.String("es-endpoints", "", "comma-separated ES endpoints (overrides SEARCH_ES_ENDPOINTS)")
	shards := flag.Int("shards", 0, "number_of_shards for the rebuilt index (0 = default)")
	replicas := flag.Int("replicas", 0, "number_of_replicas for the rebuilt index (0 = default)")
	timeout := flag.Duration("request-timeout", 30*time.Second, "per-request ES timeout")
	flag.Parse()

	cfg := es.Config{
		Endpoints:      splitList(firstNonEmpty(*esEndpoints, os.Getenv("SEARCH_ES_ENDPOINTS"))),
		Username:       os.Getenv("SEARCH_ES_USERNAME"),
		Password:       os.Getenv("SEARCH_ES_PASSWORD"),
		APIKey:         os.Getenv("SEARCH_ES_API_KEY"),
		Index:          strings.TrimSpace(firstNonEmpty(*esIndex, os.Getenv("SEARCH_ES_INDEX"))),
		RequestTimeout: *timeout,
		Schema: es.IndexSchemaConfig{
			NumberOfShards:   *shards,
			NumberOfReplicas: *replicas,
		},
	}
	if len(cfg.Endpoints) == 0 {
		log.Fatal("[search-reindex] no ES endpoints: set SEARCH_ES_ENDPOINTS or --es-endpoints")
	}
	client, err := es.NewClient(cfg)
	if err != nil {
		log.Fatalf("[search-reindex] es client: %v", err)
	}
	ctx := context.Background()

	switch {
	case *begin:
		next, err := client.BeginRebuild(ctx)
		if err != nil {
			log.Fatalf("[search-reindex] begin: %v", err)
		}
		log.Printf("[search-reindex] write alias %s -> %s; run every owner search-backfill, then --promote %s",
			client.WriteIndexName(), next, next)
	case *promote != "":
		reportCounts(ctx, client, strings.TrimSpace(*promote))
		if err := client.PromoteRebuild(ctx, strings.TrimSpace(*promote)); err != nil {
			log.Fatalf("[search-reindex] promote: %v", err)
		}
		log.Printf("[search-reindex] read alias %s -> %s; verify traffic, then --cleanup the retired index",
			client.IndexName(), strings.TrimSpace(*promote))
	case *cleanup != "":
		if err := client.CleanupRebuild(ctx, strings.TrimSpace(*cleanup)); err != nil {
			log.Fatalf("[search-reindex] cleanup: %v", err)
		}
		log.Printf("[search-reindex] retired index %s deleted", strings.TrimSpace(*cleanup))
	case *status:
		count, err := client.DocCount(ctx, client.IndexName())
		if err != nil {
			log.Fatalf("[search-reindex] status: %v", err)
		}
		log.Printf("[search-reindex] read alias %s docs=%d (write alias %s)",
			client.IndexName(), count, client.WriteIndexName())
	default:
		flag.Usage()
		os.Exit(2)
	}
}

// reportCounts prints the old/new doc counts so the operator verifies the
// backfill before promoting reads.
func reportCounts(ctx context.Context, client *es.Client, next string) {
	nextCount, err := client.DocCount(ctx, next)
	if err != nil {
		log.Fatalf("[search-reindex] count %s: %v", next, err)
	}
	currentCount, err := client.DocCount(ctx, client.IndexName())
	if err != nil {
		log.Fatalf("[search-reindex] count %s: %v", client.IndexName(), err)
	}
	log.Printf("[search-reindex] doc counts: current(read)=%d rebuilt=%d", currentCount, nextCount)
	if nextCount < currentCount {
		log.Printf("[search-reindex] WARNING: rebuilt index has fewer docs; confirm every owner backfill completed before promoting")
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func splitList(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if part = strings.TrimSpace(part); part != "" {
			out = append(out, part)
		}
	}
	return out
}
