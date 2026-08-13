package contractsview

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

var processSnapshot struct {
	sync.Once
	path string
	err  error
}

// 缓存视图的保留窗口。
//
// 每个测试进程都在 cache 下留一个 process-<pid> 快照，而只有 go-test-* 工作目录挂了
// t.Cleanup。进程被 kill、超时或 panic 时连那个也不跑，于是目录永久留下：实测积压到
// 119 个、69GB，而 .qwq_output 按 AGENTS.md 只应存放可删除、可重建的运行输出。
//
// 按时间窗而不是按「pid 是否还活着」回收：PID 会被系统复用，进程存活并不能证明它就是
// 当初写下这个目录的那次测试。个数与时间两个条件必须同时满足才删，这样并行跑的其他
// 测试包不会被删掉脚下正在读的快照。
const (
	retainedViews     = 4
	viewRetention     = time.Hour
	processViewPrefix = "process-"
	workingViewPrefix = "go-test-"
)

// pruneStaleViews 回收 parent 下陈旧的契约视图快照。
func pruneStaleViews(parent string) {
	entries, err := os.ReadDir(parent)
	if err != nil {
		return
	}
	type agedView struct {
		path     string
		modified time.Time
	}
	views := make([]agedView, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		name := entry.Name()
		if !strings.HasPrefix(name, processViewPrefix) &&
			!strings.HasPrefix(name, workingViewPrefix) {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		views = append(views, agedView{filepath.Join(parent, name), info.ModTime()})
	}
	sort.Slice(views, func(i, j int) bool {
		return views[i].modified.After(views[j].modified)
	})
	cutoff := time.Now().Add(-viewRetention)
	for index, view := range views {
		if index < retainedViews || view.modified.After(cutoff) {
			continue
		}
		os.RemoveAll(view.path)
	}
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
		pruneStaleViews(viewParent)
		processRoot := filepath.Join(
			viewParent,
			processViewPrefix+strconv.Itoa(os.Getpid()),
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
