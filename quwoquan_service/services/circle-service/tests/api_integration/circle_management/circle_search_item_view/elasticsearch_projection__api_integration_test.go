// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: project-circle-search-item-api
package api_integration

import (
	"context"
	"encoding/json"
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
		Enabled: true, Endpoints: []string{endpoint}, RequestTimeoutMs: 10_000,
		Shards: 1, Replicas: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := built.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	item := viewapp.SearchItem{
		CircleID: "circle-1", DisplayName: "洱海骑行圈", Description: "环湖骑行",
		CategoryID: "outdoor", MemberCount: 120, PostCount: 30,
		Visibility: "public", SourceVersion: 7,
	}
	sink := viewevents.NewSink(viewapp.NewProjector(built.Index), searchSnapshots{
		item: item, visible: true,
	})
	database := testsupport.StartRealMongo(t, "circle_search_item_view_api")
	checkpoints := viewpersistence.NewMongoCheckpointStore(database)
	relay := viewapp.NewRelay(lifecycleSource{events: []viewapp.LifecycleEvent{
		{EventID: "circle-updated-7", Type: "CircleUpdated", CircleID: item.CircleID, SourceVersion: item.SourceVersion, Checkpoint: "7"},
	}}, checkpoints, sink, "circle-search-api")
	if count, err := relay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	document := loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusOK)
	payload, _ := document["payload"].(map[string]any)
	if document["objectId"] != "circle-1" || payload["sourceVersion"] != "7" || payload["memberCount"] != "120" {
		t.Fatalf("canonical search document drifted: %#v", document)
	}
	if checkpoint, err := checkpoints.Load(ctx, "circle-search-api"); err != nil || checkpoint != "7" {
		t.Fatalf("projection checkpoint=%q err=%v", checkpoint, err)
	}

	if err := sink.Apply(ctx, viewapp.LifecycleEvent{
		Type: "CircleArchived", CircleID: item.CircleID, SourceVersion: item.SourceVersion + 1,
	}); err != nil {
		t.Fatal(err)
	}
	loadCircleSearchDocument(t, ctx, endpoint, "circle.circle:circle-1", http.StatusNotFound)
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
				Image:        "docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
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
