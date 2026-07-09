// Command homepage-import 把 publish 主线实体的 page.md 三件套投影进 homepage_state
// （introductionMarkdown / introductionAssets），与 content-service cmd/import 平级：
// content importer 负责 posts/entities 运行库，本命令负责主页读模型快照。
//
// 幂等语义由 application.UpsertImportedHomepages 保证（按 entityRef/title 命中即更新，
// 不重复建主页）；快照持久化走与 entity-service 相同的 MongoHomepageStateStore，
// 服务重启/冷启动时加载（与 search-backfill 的离线 reconcile 模式一致）。
//
// Usage:
//
//	go run ./services/entity-service/cmd/homepage-import \
//	  --publish-root /path/to/publish --sample-bundle publish/samples/gamma.json \
//	  --mongo-uri mongodb://localhost:27017 --entity-db quwoquan_entity \
//	  --media-base-url http://media.local:9080 --env gamma --report import-homepage-gamma.json
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/internal/application"
	"quwoquan_service/services/entity-service/internal/homepageimport"
	"quwoquan_service/services/entity-service/internal/infrastructure/persistence"
)

type sampleBundle struct {
	Environment string   `json:"environment"`
	Entities    []string `json:"entities"`
}

func main() {
	publishRoot := flag.String("publish-root", "", "publish mainline root (required)")
	bundlePath := flag.String("sample-bundle", "", "sample bundle json (optional entity filter)")
	mongoURI := flag.String("mongo-uri", "", "mongo connection uri (required unless --dry-run)")
	entityDB := flag.String("entity-db", "quwoquan_entity", "entity database name")
	stateColl := flag.String("state-collection", "homepage_state", "homepage state collection name")
	mediaBase := flag.String("media-base-url", "", "media origin/CDN base url for CAS objectKey mapping")
	env := flag.String("env", "", "environment label (for logging/report)")
	reportPath := flag.String("report", "", "write import report json to this path")
	metricsTextfile := flag.String("metrics-textfile", "", "write node_exporter textfile metrics to this path (optional)")
	dryRun := flag.Bool("dry-run", false, "load + project only; do not write mongo")
	flag.Parse()

	if *publishRoot == "" {
		log.Fatalf("[homepage-import] --publish-root is required")
	}
	var filter map[string]bool
	if *bundlePath != "" {
		raw, err := os.ReadFile(*bundlePath)
		if err != nil {
			log.Fatalf("[homepage-import] read sample bundle: %v", err)
		}
		var bundle sampleBundle
		if err := json.Unmarshal(raw, &bundle); err != nil {
			log.Fatalf("[homepage-import] parse sample bundle: %v", err)
		}
		filter = make(map[string]bool, len(bundle.Entities))
		for _, ref := range bundle.Entities {
			filter[ref] = true
		}
	}

	inputs, issues, err := homepageimport.LoadHomepageProjections(*publishRoot, filter, *mediaBase)
	if err != nil {
		log.Fatalf("[homepage-import] load projections: %v", err)
	}
	for _, issue := range issues {
		log.Printf("[homepage-import] WARN %s", issue)
	}
	log.Printf("[homepage-import] env=%s projected homepages=%d issues=%d", *env, len(inputs), len(issues))

	report := application.HomepageImportReport{
		Created:               []string{},
		Updated:               []string{},
		Skipped:               []string{},
		EntityRefToHomepageID: map[string]string{},
	}
	if *dryRun {
		log.Printf("[homepage-import] dry-run: skip mongo write")
	} else {
		if *mongoURI == "" {
			log.Fatalf("[homepage-import] --mongo-uri is required (or use --dry-run)")
		}
		ctx := context.Background()
		client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
		if err != nil {
			log.Fatalf("[homepage-import] mongo connect: %v", err)
		}
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = client.Disconnect(shutdownCtx)
		}()
		store := persistence.NewMongoHomepageStateStore(client.Database(*entityDB).Collection(*stateColl))
		service := application.NewHomepageServiceWithStore(ctx, store)
		report, err = service.UpsertImportedHomepages(ctx, inputs)
		if err != nil {
			log.Fatalf("[homepage-import] upsert failed: %v", err)
		}
	}

	if *reportPath != "" {
		payload := map[string]any{
			// v2：新增 entityRefToHomepageId 映射产物（coverage 核对面消费）。
			"schemaVersion":         "quwoquan_service.homepage_import_report/2",
			"env":                   *env,
			"dryRun":                *dryRun,
			"projected":             len(inputs),
			"created":               report.Created,
			"updated":               report.Updated,
			"skipped":               report.Skipped,
			"entityRefToHomepageId": report.EntityRefToHomepageID,
			"issues":                issues,
			"finishedAt":            time.Now().UTC().Format(time.RFC3339),
		}
		raw, _ := json.MarshalIndent(payload, "", "  ")
		if err := os.WriteFile(*reportPath, append(raw, '\n'), 0o644); err != nil {
			log.Fatalf("[homepage-import] write report: %v", err)
		}
	}
	if *metricsTextfile != "" && !*dryRun {
		if err := homepageimport.WriteImportMetricsTextfile(
			*metricsTextfile,
			*env,
			len(report.Created), len(report.Updated), len(report.Skipped), len(issues),
			time.Now().UTC(),
		); err != nil {
			log.Fatalf("[homepage-import] write metrics textfile: %v", err)
		}
	}
	log.Printf("[homepage-import] OK env=%s created=%d updated=%d skipped=%d issues=%d",
		*env, len(report.Created), len(report.Updated), len(report.Skipped), len(issues))
}
