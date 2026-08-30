package assistant_run_test

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// Compose liveness must stay on shallow /healthz. Deep dependency / worker
// probes belong on /readyz so first-scan Healthy checks cannot keep the
// container unhealthy across the compose start_period window.
//
// 探针注册已上收到 servicekit 骨架，本用例的取证点随之从服务 composition
// 移到骨架：分层语义由骨架一处保证，compose 侧只负责继续消费浅层探针。
func TestAssistantHealthProbeSplitKeepsComposeOnShallowLiveness(t *testing.T) {
	t.Parallel()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve caller path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(thisFile), "../../../.."))
	repoRoot := filepath.Clean(filepath.Join(serviceRoot, "../.."))
	kitSource, err := os.ReadFile(
		filepath.Join(repoRoot, "runtime/servicekit/bootstrap.go"),
	)
	if err != nil {
		t.Fatalf("read servicekit bootstrap.go: %v", err)
	}
	composeSource, err := os.ReadFile(filepath.Join(serviceRoot, "deploy/compose.yaml"))
	if err != nil {
		t.Fatalf("read compose.yaml: %v", err)
	}
	kitText := string(kitSource)
	composeText := string(composeSource)

	if !strings.Contains(kitText, `HandleFunc("/healthz", livenessHandler)`) {
		t.Fatal("servicekit must bind /healthz to the shallow liveness handler")
	}
	if !strings.Contains(kitText, `HandleFunc("/readyz", health.Handler())`) {
		t.Fatal("servicekit must bind /readyz to the deep health checker")
	}
	healthzStart := strings.Index(kitText, `HandleFunc("/healthz"`)
	readyzStart := strings.Index(kitText, `HandleFunc("/readyz"`)
	if readyzStart < healthzStart {
		t.Fatal("expected /healthz to be registered before /readyz")
	}
	if strings.Contains(kitText[healthzStart:readyzStart], "health.Handler()") {
		t.Fatal("shallow /healthz must not bind the deep health handler")
	}
	if !strings.Contains(composeText, "http://127.0.0.1:18087/healthz") {
		t.Fatal("compose healthcheck must probe shallow /healthz")
	}
	if strings.Contains(composeText, "http://127.0.0.1:18087/readyz") {
		t.Fatal("compose healthcheck must not probe deep /readyz")
	}
}
