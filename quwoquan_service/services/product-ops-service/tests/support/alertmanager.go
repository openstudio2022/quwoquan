package support

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

// StartAlertmanager 启动真实 Alertmanager 容器，供 ES 告警评估循环的
// 投递链 api_integration 使用。
func StartAlertmanager(
	t *testing.T,
	ctx context.Context,
) (string, func()) {
	t.Helper()
	ensureDockerHostForTestcontainers(t)
	container, err := testcontainers.GenericContainer(
		ctx,
		testcontainers.GenericContainerRequest{
			ContainerRequest: testcontainers.ContainerRequest{
				Image:        "prom/alertmanager:v0.27.0",
				SkipReaper:   true,
				ExposedPorts: []string{"9093/tcp"},
				WaitingFor: wait.ForHTTP("/-/ready").
					WithPort(nat.Port("9093/tcp")).
					WithStartupTimeout(5 * time.Minute),
			},
			Started: true,
		},
	)
	if err != nil {
		t.Fatalf("start Alertmanager testcontainer: %v", err)
	}
	endpoint, err := container.Endpoint(ctx, "http")
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("resolve Alertmanager testcontainer endpoint: %v", err)
	}
	return endpoint, func() {
		terminateCtx, terminateCancel := context.WithTimeout(
			context.Background(),
			time.Minute,
		)
		defer terminateCancel()
		if err := container.Terminate(terminateCtx); err != nil &&
			!strings.Contains(err.Error(), "removal of container") {
			t.Errorf("terminate Alertmanager testcontainer: %v", err)
		}
	}
}
