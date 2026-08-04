package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// Compose liveness must stay on shallow /healthz. Deep worker / authority
// probes belong on /readyz so first-scan Healthy(15s) cannot keep the
// container unhealthy across the compose start_period window.
func TestTravelHealthProbeSplitKeepsComposeOnShallowLiveness(t *testing.T) {
	t.Parallel()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve caller path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(thisFile), "../../../.."))
	mainSource, err := os.ReadFile(filepath.Join(serviceRoot, "cmd/api/main.go"))
	if err != nil {
		t.Fatalf("read main.go: %v", err)
	}
	composeSource, err := os.ReadFile(filepath.Join(serviceRoot, "deploy/compose.yaml"))
	if err != nil {
		t.Fatalf("read compose.yaml: %v", err)
	}
	mainText := string(mainSource)
	composeText := string(composeSource)

	if !strings.Contains(mainText, `HandleFunc("/healthz"`) {
		t.Fatal("travel-service must expose /healthz")
	}
	if !strings.Contains(mainText, `HandleFunc("/readyz"`) {
		t.Fatal("travel-service must expose deep /readyz")
	}
	if !strings.Contains(mainText, `{"status":"ok"}`) {
		t.Fatal("travel /healthz must remain a shallow liveness response")
	}
	for _, deep := range []string{
		"travel-outbox-relay",
		"travel-timeline-map-projector",
		"account-security-authority",
	} {
		if !strings.Contains(mainText, deep) {
			t.Fatalf("travel /readyz must still register deep check %q", deep)
		}
	}
	healthzBlockStart := strings.Index(mainText, `HandleFunc("/healthz"`)
	readyzBlockStart := strings.Index(mainText, `HandleFunc("/readyz"`)
	if healthzBlockStart < 0 || readyzBlockStart < 0 {
		t.Fatal("missing health probe handlers")
	}
	healthzWindow := mainText[healthzBlockStart:readyzBlockStart]
	for _, deep := range []string{
		"travel-outbox-relay",
		"travel-timeline-map-projector",
		"account-security-authority",
		"outboxRelay.Healthy",
		"projectionConsumer.Healthy",
		"CheckAccountSecurityAuthority",
	} {
		if strings.Contains(healthzWindow, deep) {
			t.Fatalf("shallow /healthz must not embed deep check %q", deep)
		}
	}
	if !strings.Contains(composeText, "http://127.0.0.1:18093/healthz") {
		t.Fatal("compose healthcheck must probe shallow /healthz")
	}
	if strings.Contains(composeText, "http://127.0.0.1:18093/readyz") {
		t.Fatal("compose healthcheck must not probe deep /readyz")
	}
}
