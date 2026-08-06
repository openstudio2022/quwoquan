// Command homepage-import 按 immutable release payload把 entity snapshot 投影进 homepages
// （introductionMarkdown / introductionAssets），与 content-service cmd/import 平级：
// content importer 负责 posts/entities 运行库，本命令负责主页读模型快照。
//
// 幂等语义由 application.ReconcileImportedHomepages 保证。来源身份固定为
// qwq_data + entityRef；sync 只会下线该来源中未声明的主页，不会碰人工或官方 seed。
// 持久化走 Homepage 对象 Store，以 sourceOwner+sourceEntityRef 幂等 upsert。
//
// Usage:
//
//	go run ./services/entity-service/cmd/homepage-import \
//	  --release-root /path/to/release/<releaseId> \
//	  --mongo-uri mongodb://localhost:27017 --entity-db quwoquan_entity \
//	  --media-image-base-url http://media.local:9080 --env gamma --report import-homepage-gamma.json
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"path/filepath"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

type releaseDesiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Entities []string `json:"entities"`
	} `json:"desiredRefs"`
}

func main() {
	releaseRoot := flag.String("release-root", "", "immutable release root with payload/desired_state.json (required)")
	mongoURI := flag.String("mongo-uri", "", "mongo connection uri (required unless --dry-run)")
	entityDB := flag.String("entity-db", "quwoquan_entity", "entity database name")
	mediaImageBase := flag.String("media-image-base-url", "", "image media public base URL")
	env := flag.String("env", "", "environment label (for logging/report)")
	runID := flag.String("run-id", "", "environment import run identity (required)")
	reportPath := flag.String("report", "", "write import report json to this path")
	metricsTextfile := flag.String("metrics-textfile", "", "write node_exporter textfile metrics to this path (optional)")
	mode := flag.String("mode", string(application.HomepageImportModeUpsert), "reconciliation mode: upsert|sync")
	dryRun := flag.Bool("dry-run", false, "load + project only; do not write mongo")
	flag.Parse()

	if *releaseRoot == "" {
		log.Fatalf("[homepage-import] --release-root is required; full-tree import and sample bundle fallback are forbidden")
	}
	if *runID == "" {
		log.Fatalf("[homepage-import] --run-id is required")
	}
	raw, err := os.ReadFile(filepath.Join(*releaseRoot, "payload", "desired_state.json"))
	if err != nil {
		log.Fatalf("[homepage-import] read desired state: %v", err)
	}
	var desired releaseDesiredState
	if err := json.Unmarshal(raw, &desired); err != nil {
		log.Fatalf("[homepage-import] parse desired state: %v", err)
	}
	if desired.Schema != "quwoquan_data.release_desired_state" || desired.ReleaseID == "" {
		log.Fatalf("[homepage-import] unsupported desired state schema=%q releaseId=%q", desired.Schema, desired.ReleaseID)
	}
	importMode := application.HomepageImportMode(*mode)
	if importMode != application.HomepageImportModeUpsert && importMode != application.HomepageImportModeSync {
		log.Fatalf("[homepage-import] --mode must be upsert or sync")
	}
	filter := make(map[string]bool, len(desired.DesiredRefs.Entities))
	for _, ref := range desired.DesiredRefs.Entities {
		filter[ref] = true
	}

	objectRoot := filepath.Join(*releaseRoot, "payload", "objects")
	objectInfo, err := os.Stat(objectRoot)
	if err != nil || !objectInfo.IsDir() {
		log.Fatalf("[homepage-import] release object closure unavailable: %s: %v", objectRoot, err)
	}
	releaseAssets, err := runtimemedia.LoadReleaseMediaAssets(*releaseRoot, desired.ReleaseID)
	if err != nil {
		log.Fatalf("[homepage-import] load release media authority: %v", err)
	}
	inputs, issues, err := homepageimport.LoadHomepageProjections(
		objectRoot,
		filter,
		releaseAssets,
		runtimemedia.MediaDeliveryBases{Image: *mediaImageBase},
	)
	if err != nil {
		log.Fatalf("[homepage-import] load projections: %v", err)
	}
	if issues == nil {
		issues = []string{}
	}
	for _, issue := range issues {
		log.Printf("[homepage-import] WARN %s", issue)
	}
	log.Printf("[homepage-import] env=%s projected homepages=%d issues=%d", *env, len(inputs), len(issues))

	report := application.HomepageImportReport{
		Mode:                  importMode,
		SourceOwner:           "qwq_data",
		Created:               []string{},
		Updated:               []string{},
		Offlined:              []string{},
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
		store := homepagepersistence.NewMongoHomepageStore(client.Database(*entityDB))
		if err := store.EnsureIndexes(ctx); err != nil {
			log.Fatalf("[homepage-import] ensure homepage indexes: %v", err)
		}
		service := application.NewHomepageServiceWithStore(ctx, store)
		report, err = service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
			Mode:            importMode,
			SourceOwner:     "qwq_data",
			SourceReleaseID: desired.ReleaseID,
			RunID:           *runID,
			Inputs:          inputs,
		})
		if err != nil {
			log.Fatalf("[homepage-import] reconcile failed: %v", err)
		}
	}

	if *reportPath != "" {
		payload := map[string]any{
			"schema":                "quwoquan_service.homepage_import_report",
			"releaseId":             desired.ReleaseID,
			"env":                   *env,
			"dryRun":                *dryRun,
			"mode":                  report.Mode,
			"sourceOwner":           report.SourceOwner,
			"projected":             len(inputs),
			"created":               report.Created,
			"updated":               report.Updated,
			"offlined":              report.Offlined,
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
	log.Printf("[homepage-import] OK env=%s mode=%s created=%d updated=%d offlined=%d skipped=%d issues=%d",
		*env, report.Mode, len(report.Created), len(report.Updated), len(report.Offlined), len(report.Skipped), len(issues))
}
