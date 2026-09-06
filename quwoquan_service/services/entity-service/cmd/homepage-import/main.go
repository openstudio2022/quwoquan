// Command homepage-import verifies one immutable Data release and stages its
// Homepage-owned projections under the exact environment/sourceOwner/releaseId/
// manifestDigest identity. It never publishes release-owned fields into the
// Homepage aggregate and never offlines the currently visible release. Public
// reads are selected later by the Content active tuple.
//
// Usage:
//
//	go run ./services/entity-service/cmd/homepage-import \
//	  --release-root /path/to/release/<releaseId> --env gamma \
//	  --mongo-uri mongodb://localhost:27017 --entity-db quwoquan_entity \
//	  --media-image-base-url http://media.local:9080 --run-id <runId> \
//	  --report import-homepage-gamma.json
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimedatarelease "quwoquan_service/runtime/datarelease"
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
	manifestDigest := flag.String("manifest-digest", "", "exact immutable payload sha256 (required)")
	dryRun := flag.Bool("dry-run", false, "load + project only; do not write mongo")
	flag.Parse()

	if *releaseRoot == "" {
		log.Fatalf("[homepage-import] --release-root is required; full-tree import and sample bundle fallback are forbidden")
	}
	if *runID == "" {
		log.Fatalf("[homepage-import] --run-id is required")
	}
	releaseTuple, err := runtimedatarelease.Load(*releaseRoot)
	if err != nil {
		log.Fatalf("[homepage-import] load immutable release tuple: %v", err)
	}
	if string(releaseTuple.SourceOwner) != "qwq_data" {
		log.Fatalf("[homepage-import] source owner must be qwq_data")
	}
	raw, err := os.ReadFile(filepath.Join(*releaseRoot, "payload", "desired_state.json"))
	if err != nil {
		log.Fatalf("[homepage-import] read desired state: %v", err)
	}
	var desired releaseDesiredState
	if err := json.Unmarshal(raw, &desired); err != nil {
		log.Fatalf("[homepage-import] parse desired state: %v", err)
	}
	if desired.Schema != "quwoquan_data.release_desired_state" || desired.ReleaseID == "" || desired.ReleaseID != releaseTuple.ReleaseID {
		log.Fatalf("[homepage-import] unsupported desired state schema=%q releaseId=%q", desired.Schema, desired.ReleaseID)
	}
	if strings.TrimSpace(*manifestDigest) != "" && strings.TrimSpace(*manifestDigest) != string(releaseTuple.PayloadSHA256) {
		log.Fatalf("[homepage-import] --manifest-digest differs from verified immutable release tuple")
	}
	*manifestDigest = string(releaseTuple.PayloadSHA256)
	if _, identityErr := application.NormalizeHomepageReleaseIdentity(application.HomepageReleaseIdentity{
		Environment: *env, SourceOwner: "qwq_data", ReleaseID: desired.ReleaseID,
		ManifestDigest: *manifestDigest,
	}); identityErr != nil {
		log.Fatalf("[homepage-import] --env and canonical --manifest-digest are required: %v", identityErr)
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
	headerRaw, err := os.ReadFile(filepath.Join(*releaseRoot, "payload", "release.json"))
	if err != nil {
		log.Fatalf("[homepage-import] read release header: %v", err)
	}
	var header struct {
		ReleaseClass string `json:"releaseClass"`
	}
	if err := json.Unmarshal(headerRaw, &header); err != nil {
		log.Fatalf("[homepage-import] parse release header: %v", err)
	}
	if strings.TrimSpace(header.ReleaseClass) != string(releaseTuple.ReleaseClass) {
		log.Fatalf("[homepage-import] release class differs from verified immutable release tuple")
	}
	releaseAssets, err := runtimemedia.LoadReleaseMediaAssets(
		*releaseRoot,
		desired.ReleaseID,
		strings.TrimSpace(header.ReleaseClass),
	)
	if err != nil {
		log.Fatalf("[homepage-import] load release media authority: %v", err)
	}
	inputs, issues, err := homepageimport.LoadHomepageProjections(
		objectRoot,
		filter,
		releaseAssets,
		runtimemedia.MediaDeliveryBases{Image: *mediaImageBase},
		strings.TrimSpace(header.ReleaseClass),
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

	report := application.HomepageReleaseStageReport{
		Identity: application.HomepageReleaseIdentity{
			Environment: *env, SourceOwner: "qwq_data", ReleaseID: desired.ReleaseID,
			ManifestDigest: *manifestDigest,
		},
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
		report, err = service.StageHomepageReleaseCandidate(ctx, application.HomepageReleaseStageRequest{
			Identity: application.HomepageReleaseIdentity{
				Environment: *env, SourceOwner: "qwq_data", ReleaseID: desired.ReleaseID,
				ManifestDigest: *manifestDigest,
			},
			Inputs: inputs,
		}, time.Now().UTC().Truncate(time.Millisecond))
		if err != nil {
			log.Fatalf("[homepage-import] stage release candidate failed: %v", err)
		}
	}

	if *reportPath != "" {
		payload := map[string]any{
			"schema":                 "quwoquan_service.homepage_import_report",
			"releaseId":              desired.ReleaseID,
			"env":                    *env,
			"dryRun":                 *dryRun,
			"sourceOwner":            report.Identity.SourceOwner,
			"manifestDigest":         report.Identity.ManifestDigest,
			"projectionVersion":      report.ProjectionVersion,
			"closureDigest":          report.ClosureDigest,
			"expected":               report.ExpectedCount,
			"projected":              report.ProjectedCount,
			"entityRefToHomepageId":  report.EntityRefToHomepageID,
			"entityRefMappingDigest": report.EntityRefMappingDigest,
			"replayed":               report.Replayed,
			"verifiedAt":             report.VerifiedAt,
			"issues":                 issues,
			"finishedAt":             time.Now().UTC().Format(time.RFC3339),
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
			report.ProjectedCount, 0, 0, len(issues),
			time.Now().UTC(),
		); err != nil {
			log.Fatalf("[homepage-import] write metrics textfile: %v", err)
		}
	}
	log.Printf("[homepage-import] OK env=%s release=%s projected=%d replayed=%t issues=%d",
		*env, desired.ReleaseID, report.ProjectedCount, report.Replayed, len(issues))
}
