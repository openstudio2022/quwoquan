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

// StartElasticsearch returns either the explicitly configured real provider
// endpoint or a dedicated Elasticsearch testcontainer. API integration tests
// use this helper so object-level evidence exercises the production adapter
// without duplicating provider bootstrap policy.
func StartElasticsearch(
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
				Image:        "docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
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
		t.Fatalf("start Elasticsearch testcontainer: %v", err)
	}
	endpoint, err := container.Endpoint(ctx, "http")
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("resolve Elasticsearch testcontainer endpoint: %v", err)
	}
	return endpoint, func() {
		terminateCtx, terminateCancel := context.WithTimeout(
			context.Background(),
			time.Minute,
		)
		defer terminateCancel()
		if err := container.Terminate(terminateCtx); err != nil &&
			!strings.Contains(err.Error(), "removal of container") {
			t.Errorf("terminate Elasticsearch testcontainer: %v", err)
		}
	}
}

func ensureDockerHostForTestcontainers(t *testing.T) {
	t.Helper()
	t.Setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) != "" {
		return
	}
	output, err := exec.Command(
		"docker",
		"context",
		"inspect",
		"--format",
		"{{.Endpoints.docker.Host}}",
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
