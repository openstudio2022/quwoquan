package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestSearchHealthProbeSplitKeepsComposeOnShallowLiveness(t *testing.T) {
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
	if !strings.Contains(mainText, `HandleFunc("/healthz"`) ||
		!strings.Contains(mainText, `HandleFunc("/readyz"`) ||
		!strings.Contains(mainText, `{"status":"ok"}`) {
		t.Fatal("search-service must expose shallow /healthz and deep /readyz")
	}
	healthzBlockStart := strings.Index(mainText, `HandleFunc("/healthz"`)
	readyzBlockStart := strings.Index(mainText, `HandleFunc("/readyz"`)
	if healthzBlockStart < 0 || readyzBlockStart < 0 || healthzBlockStart > readyzBlockStart {
		t.Fatal("health probe handler order is invalid")
	}
	healthzWindow := mainText[healthzBlockStart:readyzBlockStart]
	for _, deep := range []string{
		"experiment-policy-consumer",
		"feedback-signal-relay",
		"user-account-closed-consumer",
		"CheckAccountSecurityAuthority",
	} {
		if strings.Contains(healthzWindow, deep) {
			t.Fatalf("shallow /healthz must not embed deep check %q", deep)
		}
	}
	if !strings.Contains(composeText, "http://127.0.0.1:18095/healthz") {
		t.Fatal("compose healthcheck must probe shallow /healthz")
	}
}
