package contractsview

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

// Build materializes the service-owned contracts into a disposable compiler
// view. Tests must not depend on the retired global domain contract tree or on
// a view left behind by a previous Make invocation.
func Build(t testing.TB) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve contracts view helper path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", ".."))
	repositoryRoot := filepath.Dir(serviceRoot)
	viewParent := filepath.Join(
		repositoryRoot,
		".qwq_output",
		"env",
		"repo",
		"local",
		"test-contract-views",
		"cache",
	)
	if err := os.MkdirAll(viewParent, 0o755); err != nil {
		t.Fatalf("create contract view parent: %v", err)
	}
	workingRoot, err := os.MkdirTemp(viewParent, "go-test-")
	if err != nil {
		t.Fatalf("create contract view working root: %v", err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(workingRoot); err != nil {
			t.Errorf("remove contract view: %v", err)
		}
	})
	output := filepath.Join(workingRoot, "metadata")
	script := filepath.Join(serviceRoot, "scripts", "contracts", "build_service_contract_view.py")
	command := exec.Command("python3", script, "--output", output)
	command.Dir = repositoryRoot
	command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if payload, err := command.CombinedOutput(); err != nil {
		t.Fatalf("build service contract view: %v\n%s", err, payload)
	}
	return output
}
