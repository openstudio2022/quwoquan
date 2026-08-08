package contractsview

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"testing"
)

var processSnapshot struct {
	sync.Once
	path string
	err  error
}

// Build materializes the service-owned contracts into a disposable compiler
// view. Tests must not depend on the retired global domain contract tree or on
// a view left behind by a previous Make invocation.
func Build(t testing.TB) string {
	t.Helper()
	serviceRoot := serviceRootPath(t)
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
	processSnapshot.Do(func() {
		processRoot := filepath.Join(
			viewParent,
			"process-"+strconv.Itoa(os.Getpid()),
		)
		processSnapshot.path = filepath.Join(processRoot, "metadata")
		script := filepath.Join(
			serviceRoot, "scripts", "contracts", "build_service_contract_view.py",
		)
		command := exec.Command("python3", script, "--output", processSnapshot.path)
		command.Dir = repositoryRoot
		command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
		if payload, err := command.CombinedOutput(); err != nil {
			processSnapshot.err = fmt.Errorf("build process contract snapshot: %w\n%s", err, payload)
		}
	})
	if processSnapshot.err != nil {
		t.Fatalf("build service contract view: %v", processSnapshot.err)
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
	if err := os.MkdirAll(output, 0o755); err != nil {
		t.Fatalf("create contract view output: %v", err)
	}
	command := exec.Command("cp", "-R", processSnapshot.path+string(filepath.Separator)+".", output)
	if payload, err := command.CombinedOutput(); err != nil {
		t.Fatalf("copy process contract snapshot: %v\n%s", err, payload)
	}
	return output
}

// RepositoryRoot 返回仓库根。派生 readinessEvidence 需要真实源码树，而 Build 返回的
// metadata 视图只含 YAML 且落在 .qwq_output 下，所以两者必须来自同一个物理锚点。
func RepositoryRoot(t testing.TB) string {
	t.Helper()
	return filepath.Dir(serviceRootPath(t))
}

func serviceRootPath(t testing.TB) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve contracts view helper path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", ".."))
}
