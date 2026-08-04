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
func TestAssistantHealthProbeSplitKeepsComposeOnShallowLiveness(t *testing.T) {
	t.Parallel()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve caller path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(thisFile), "../../../.."))
	httpSource, err := os.ReadFile(filepath.Join(serviceRoot, "cmd/api/composition_http_server.go"))
	if err != nil {
		t.Fatalf("read composition_http_server.go: %v", err)
	}
	composeSource, err := os.ReadFile(filepath.Join(serviceRoot, "deploy/compose.yaml"))
	if err != nil {
		t.Fatalf("read compose.yaml: %v", err)
	}
	httpText := string(httpSource)
	composeText := string(composeSource)

	if !strings.Contains(httpText, `HandleFunc("/healthz"`) {
		t.Fatal("assistant-service must expose /healthz")
	}
	if !strings.Contains(httpText, `HandleFunc("/readyz"`) {
		t.Fatal("assistant-service must expose deep /readyz")
	}
	if !strings.Contains(httpText, `{"status":"ok"}`) {
		t.Fatal("assistant /healthz must remain a shallow liveness response")
	}
	healthzBlockStart := strings.Index(httpText, `HandleFunc("/healthz"`)
	readyzBlockStart := strings.Index(httpText, `HandleFunc("/readyz"`)
	if healthzBlockStart < 0 || readyzBlockStart < 0 {
		t.Fatal("missing health probe handlers")
	}
	if readyzBlockStart < healthzBlockStart {
		t.Fatal("expected /healthz to be registered before /readyz")
	}
	healthzWindow := httpText[healthzBlockStart:readyzBlockStart]
	if strings.Contains(healthzWindow, "healthChecker.Handler()") {
		t.Fatal("shallow /healthz must not bind the deep healthChecker handler")
	}
	if !strings.Contains(httpText[readyzBlockStart:], "healthChecker.Handler()") {
		t.Fatal("deep /readyz must bind healthChecker.Handler()")
	}
	if !strings.Contains(composeText, "http://127.0.0.1:18087/healthz") {
		t.Fatal("compose healthcheck must probe shallow /healthz")
	}
	if strings.Contains(composeText, "http://127.0.0.1:18087/readyz") {
		t.Fatal("compose healthcheck must not probe deep /readyz")
	}
}
