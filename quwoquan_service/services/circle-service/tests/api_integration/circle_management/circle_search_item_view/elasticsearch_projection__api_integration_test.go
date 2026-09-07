// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: project-circle-search-item-api
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	"quwoquan_service/runtime/search/es"
	viewevents "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/adapters/inbound/events"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
	viewes "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/infrastructure/elasticsearch"
	viewpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

type searchSnapshots struct {
	item    viewapp.SearchItem
	visible bool
}

func (source searchSnapshots) LoadSearchItem(context.Context, string) (viewapp.SearchItem, bool, error) {
	return source.item, source.visible, nil
}

type lifecycleSource struct {
	events []viewapp.LifecycleEvent
}

func (source lifecycleSource) ReadAfter(_ context.Context, checkpoint string, _ int) ([]viewapp.LifecycleEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return source.events, nil
}

func TestCircleSearchItemViewProductionSinkProjectsIntoRealElasticsearch(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	endpoint, cleanup := startCircleSearchElasticsearch(t, ctx)
	defer cleanup()

	built, err := viewes.Build(viewes.Config{
		Enabled: true, Endpoints: []string{endpoint}, RequestTimeoutMs: 30_000,
		Shards: 1, Replicas: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := built.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	itemV2 := viewapp.SearchItem{
		CircleID: "circle-1", DisplayName: "洱海骑行圈 v2", Description: "环湖骑行",
		CategoryID: "outdoor", MemberCount: 120, PostCount: 30,
		Visibility: "public", SourceVersion: 2,
	}
	sink := viewevents.NewSink(viewapp.NewProjector(built.Index), searchSnapshots{
		item: itemV2, visible: true,
	})
	database := testsupport.StartRealMongo(t, "circle_search_item_view_api")
	checkpoints := viewpersistence.NewMongoCheckpointStore(database)
	relay := viewapp.NewRelay(lifecycleSource{events: []viewapp.LifecycleEvent{
		{EventID: "circle-updated-2", Type: "CircleUpdated", CircleID: itemV2.CircleID, SourceVersion: itemV2.SourceVersion, Checkpoint: "2"},
	}}, checkpoints, sink, "circle-search-api")
	if count, err := relay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	document := loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	payload, _ := document["payload"].(map[string]any)
	if document["objectId"] != "circle-1" || document["title"] != itemV2.DisplayName ||
		document["sourceVersion"] != float64(2) || document["deleted"] != false ||
		payload["sourceVersion"] != "2" || payload["memberCount"] != "120" {
		t.Fatalf("canonical v2 search document drifted: %#v", document)
	}
	if checkpoint, err := checkpoints.Load(ctx, "circle-search-api"); err != nil || checkpoint != "2" {
		t.Fatalf("projection checkpoint=%q err=%v", checkpoint, err)
	}

	lateV1 := itemV2
	lateV1.DisplayName = "late version one"
	lateV1.SourceVersion = 1
	if applied, err := built.Index.UpsertIfNewer(ctx, lateV1); err != nil || applied {
		t.Fatalf("late v1 applied=%v err=%v; external versioning must reject it", applied, err)
	}
	document = loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	if document["title"] != itemV2.DisplayName || document["sourceVersion"] != float64(2) || document["deleted"] != false {
		t.Fatalf("late v1 overwrote v2: %#v", document)
	}

	// Equal external versions are classified by canonical source digest: exact
	// replay is a no-op, while divergent facts fail closed.
	if applied, err := built.Index.UpsertIfNewer(ctx, itemV2); err != nil || applied {
		t.Fatalf("exact v2 replay applied=%v err=%v", applied, err)
	}
	conflictingV2 := itemV2
	conflictingV2.DisplayName = "conflicting version two"
	if applied, err := built.Index.UpsertIfNewer(ctx, conflictingV2); applied || !errors.Is(err, es.ErrSameVersionDigestConflict) {
		t.Fatalf("conflicting v2 applied=%v err=%v", applied, err)
	}
	document = loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	if document["title"] != itemV2.DisplayName || document["sourceVersion"] != float64(2) {
		t.Fatalf("equal-version conflict changed the winner: %#v", document)
	}

	concurrentItems := []viewapp.SearchItem{itemV2, itemV2}
	concurrentItems[0].DisplayName = "version four"
	concurrentItems[0].SourceVersion = 4
	concurrentItems[1].DisplayName = "version five"
	concurrentItems[1].SourceVersion = 5
	type writeResult struct {
		version int64
		applied bool
		err     error
	}
	start := make(chan struct{})
	results := make(chan writeResult, len(concurrentItems))
	for _, item := range concurrentItems {
		go func(candidate viewapp.SearchItem) {
			<-start
			applied, err := built.Index.UpsertIfNewer(ctx, candidate)
			results <- writeResult{version: candidate.SourceVersion, applied: applied, err: err}
		}(item)
	}
	close(start)
	v5Applied := false
	for range concurrentItems {
		result := <-results
		if result.err != nil {
			t.Fatalf("concurrent v%d: %v", result.version, result.err)
		}
		if result.version == 5 {
			v5Applied = result.applied
		}
	}
	if !v5Applied {
		t.Fatal("v5 must win regardless of concurrent v4 arrival order")
	}
	document = loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	if document["title"] != "version five" || document["sourceVersion"] != float64(5) || document["deleted"] != false {
		t.Fatalf("concurrent v4/v5 did not converge to v5: %#v", document)
	}

	if applied, err := built.Index.DeleteIfNotOlder(ctx, itemV2.CircleID, 6); err != nil || !applied {
		t.Fatalf("v6 tombstone applied=%v err=%v", applied, err)
	}
	resurrectionV2 := itemV2
	resurrectionV2.DisplayName = "late resurrection v2"
	if applied, err := built.Index.UpsertIfNewer(ctx, resurrectionV2); err != nil || applied {
		t.Fatalf("late upsert v2 after tombstone applied=%v err=%v", applied, err)
	}
	if applied, err := built.Index.DeleteIfNotOlder(ctx, itemV2.CircleID, 6); err != nil || applied {
		t.Fatalf("same-version tombstone replay applied=%v err=%v", applied, err)
	}
	equalVersionResurrection := itemV2
	equalVersionResurrection.DisplayName = "same-version resurrection v6"
	equalVersionResurrection.SourceVersion = 6
	if applied, err := built.Index.UpsertIfNewer(ctx, equalVersionResurrection); applied || !errors.Is(err, es.ErrSameVersionDigestConflict) {
		t.Fatalf("same-version upsert against tombstone applied=%v err=%v", applied, err)
	}
	tombstone := loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	if tombstone["deleted"] != true || tombstone["sourceVersion"] != float64(6) ||
		!strings.HasPrefix(tombstone["sourceDigest"].(string), "sha256:") || len(tombstone) != 5 {
		t.Fatalf("persistent CircleSearchItemView tombstone drifted: %#v", tombstone)
	}

	visible := itemV2
	visible.CircleID = "circle-visible"
	visible.DisplayName = "visible control"
	visible.SourceVersion = 1
	if applied, err := built.Index.UpsertIfNewer(ctx, visible); err != nil || !applied {
		t.Fatalf("visible control applied=%v err=%v", applied, err)
	}
	visibleSource := loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-visible", http.StatusOK)
	if visibleSource["sourceVersion"] != float64(1) || visibleSource["deleted"] != false {
		t.Fatalf("visible control source-version fields drifted: %#v", visibleSource)
	}
	if err := built.Client.Refresh(ctx); err != nil {
		t.Fatal(err)
	}
	candidates, err := built.Client.Search(ctx, built.Client.IndexName(), map[string]any{
		"size":  20,
		"query": map[string]any{"match_all": map[string]any{}},
	})
	if err != nil {
		t.Fatal(err)
	}
	foundVisible := false
	for _, candidate := range candidates {
		switch candidate.Document.ObjectID {
		case itemV2.CircleID:
			t.Fatalf("default search returned deleted tombstone: %+v", candidate.Document)
		case visible.CircleID:
			foundVisible = true
		}
	}
	if !foundVisible {
		t.Fatalf("default search omitted visible control: %+v", candidates)
	}
}
func loadCircleSearchDocument(
	t *testing.T,
	ctx context.Context,
	endpoint string,
	documentID string,
	wantStatus int,
) map[string]any {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		strings.TrimRight(endpoint, "/")+"/"+es.DefaultIndex+"/_doc/"+url.PathEscape(documentID),
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != wantStatus {
		t.Fatalf("Elasticsearch document status=%d want=%d body=%s", response.StatusCode, wantStatus, body)
	}
	if wantStatus == http.StatusNotFound {
		return nil
	}
	var envelope struct {
		Source map[string]any `json:"_source"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		t.Fatal(err)
	}
	return envelope.Source
}

func startCircleSearchElasticsearch(t *testing.T, ctx context.Context) (string, func()) {
	t.Helper()
	if endpoint := strings.TrimSpace(os.Getenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT")); endpoint != "" {
		return strings.TrimRight(endpoint, "/"), func() {}
	}
	t.Setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) == "" {
		output, err := exec.Command(
			"docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}",
		).Output()
		if err != nil {
			t.Fatalf("resolve Docker context for Elasticsearch testcontainer: %v", err)
		}
		dockerHost := strings.TrimSpace(string(output))
		if dockerHost == "" {
			t.Fatal("active Docker context has no endpoint")
		}
		t.Setenv("DOCKER_HOST", dockerHost)
	}
	environment := map[string]string{
		"discovery.type":                                    "single-node",
		"xpack.security.enabled":                            "false",
		"xpack.security.http.ssl.enabled":                   "false",
		"cluster.routing.allocation.disk.threshold_enabled": "false",
		"ES_JAVA_OPTS":                                      "-Xms512m -Xmx512m",
	}
	if runtime.GOARCH == "arm64" {
		environment["CLI_JAVA_OPTS"] = "-XX:UseSVE=0"
		environment["ES_JAVA_OPTS"] = "-XX:UseSVE=0 -Xms512m -Xmx512m"
	}
	container, err := testcontainers.GenericContainer(
		ctx,
		testcontainers.GenericContainerRequest{
			ContainerRequest: testcontainers.ContainerRequest{
				Image:        "quwoquan/elasticsearch-cjk:8.13.4",
				SkipReaper:   true,
				Env:          environment,
				ExposedPorts: []string{"9200/tcp"},
				WaitingFor: wait.ForHTTP("/_ilm/status").
					WithPort(nat.Port("9200/tcp")).
					WithStartupTimeout(4 * time.Minute),
			},
			Started: true,
		},
	)
	if err != nil {
		t.Fatalf("start Elasticsearch testcontainer: %v", err)
	}
	endpoint, err := container.Endpoint(ctx, "http")
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("resolve Elasticsearch testcontainer endpoint: %v", err)
	}
	return endpoint, func() {
		terminateCtx, terminateCancel := context.WithTimeout(context.Background(), time.Minute)
		defer terminateCancel()
		if err := container.Terminate(terminateCtx); err != nil &&
			!strings.Contains(err.Error(), "removal of container") {
			t.Errorf("terminate Elasticsearch testcontainer: %v", err)
		}
	}
}
