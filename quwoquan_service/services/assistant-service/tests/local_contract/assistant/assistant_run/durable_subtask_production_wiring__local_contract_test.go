// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
package assistant_run_test

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestProductionAgentLoopWiresDurableSubtasksToCanonicalRunRepository(
	t *testing.T,
) {
	t.Parallel()
	serviceRoot := durableSubtaskProductionServiceRoot(t)
	registry := durableSubtaskProductionSource(
		t,
		filepath.Join(serviceRoot, "cmd", "api", "assistant_tool_registry.go"),
	)
	composition := durableSubtaskProductionSource(
		t,
		filepath.Join(serviceRoot, "cmd", "api", "composition_assistant_runtime.go"),
	)

	for _, required := range []string{
		"runs runruntime.Repository,\n\tworkerID string,",
		"if runs == nil {\n\t\treturn nil, fmt.Errorf(\"assistant run repository is required\")\n\t}",
		"workerID = strings.TrimSpace(workerID)",
		"if workerID == \"\" {\n\t\treturn nil, fmt.Errorf(\"assistant durable subtask worker ID is required\")\n\t}",
		"loop.DurableSubtasks = orchestration.NewDurableSubtaskCoordinator(",
		"orchestration.NewRepositoryDurableSubtaskStore(runs, nil),",
		"assistantDurableSubtaskLeaseTTL          = 15 * time.Second",
		"assistantDurableSubtaskHeartbeatInterval = 3 * time.Second",
	} {
		if !strings.Contains(registry, required) {
			t.Errorf("production AgentLoop durable wiring missing %q", required)
		}
	}
	if !strings.Contains(
		composition,
		"deps.runRepository,\n\t\truntime.instanceID+\":assistant-subtask\",",
	) {
		t.Fatal("production composition does not use an instance-scoped durable subtask worker ID")
	}
	if strings.Contains(registry, "NewMemory") ||
		strings.Contains(registry, "InMemory") {
		t.Fatal("production durable subtask wiring must not fall back to memory storage")
	}
}

func durableSubtaskProductionServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve durable subtask wiring test path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "main.go")); err != nil {
		t.Fatalf("resolve assistant-service root: %v", err)
	}
	return root
}

func durableSubtaskProductionSource(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read production wiring %s: %v", path, err)
	}
	return string(payload)
}
