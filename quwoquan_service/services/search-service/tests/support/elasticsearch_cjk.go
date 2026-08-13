package support

import (
	"context"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

// ElasticsearchCJKImage is the production search image: the pinned official
// base plus analysis-ik / analysis-pinyin. Golden-query relevance evidence is
// only meaningful against the same analyzer chain production runs, so the
// substitute image is not an acceptable stand-in here.
const ElasticsearchCJKImage = "quwoquan/elasticsearch-cjk:8.13.4"

// StartElasticsearchCJK returns either the explicitly configured real provider
// endpoint (QWQ_TEST_ELASTICSEARCH_ENDPOINT) or a dedicated testcontainer
// running the production CJK image. Mirrors the product-ops provider bootstrap
// policy so object-level evidence exercises the production adapter.
func StartElasticsearchCJK(
	t *testing.T,
	ctx context.Context,
) (string, func()) {
	t.Helper()
	if endpoint := strings.TrimSpace(os.Getenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT")); endpoint != "" {
		return strings.TrimRight(endpoint, "/"), func() {}
	}
	ensureDockerHostForTestcontainers(t)
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
				Image:        ElasticsearchCJKImage,
				SkipReaper:   true,
				Env:          environment,
				ExposedPorts: []string{"9200/tcp"},
				WaitingFor: wait.ForHTTP("/_ilm/status").
					WithPort(nat.Port("9200/tcp")).
					WithStartupTimeout(25 * time.Minute),
			},
			Started: true,
		},
	)
	if err != nil {
		t.Fatalf("start Elasticsearch CJK testcontainer: %v", err)
	}
	endpoint, err := container.Endpoint(ctx, "http")
	if err != nil {
		_ = container.Terminate(ctx)
		t.Fatalf("resolve Elasticsearch CJK endpoint: %v", err)
	}
	return strings.TrimRight(endpoint, "/"), func() {
		terminateCtx, cancel := context.WithTimeout(context.Background(), time.Minute)
		defer cancel()
		_ = container.Terminate(terminateCtx)
	}
}

// ensureDockerHostForTestcontainers resolves the local docker socket the same
// way the sibling provider helpers do (colima / Docker Desktop variants).
func ensureDockerHostForTestcontainers(t *testing.T) {
	t.Helper()
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) != "" {
		return
	}
	command := exec.Command("docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
	output, err := command.Output()
	if err != nil {
		return
	}
	host := strings.TrimSpace(string(output))
	if host != "" {
		t.Setenv("DOCKER_HOST", host)
	}
}
