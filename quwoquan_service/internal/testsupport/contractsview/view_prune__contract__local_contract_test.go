// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
package contractsview

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// 契约视图快照的回收契约。
//
// 只有 go-test-* 工作目录挂了 t.Cleanup；process-<pid> 快照从不删除，进程被 kill 或
// panic 时连 Cleanup 也不跑。实测积压到 119 个目录、69GB。回收必须同时保证长期不膨胀
// 与并发安全 —— 后者是这类清理最容易写错的地方。

func makeView(t *testing.T, parent, name string, age time.Duration) string {
	t.Helper()
	path := filepath.Join(parent, name)
	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatalf("create view %s: %v", name, err)
	}
	stamp := time.Now().Add(-age)
	if err := os.Chtimes(path, stamp, stamp); err != nil {
		t.Fatalf("age view %s: %v", name, err)
	}
	return path
}

func TestPruneReclaimsViewsBeyondBothWindows(t *testing.T) {
	parent := t.TempDir()
	stale := make([]string, 0, retainedViews+5)
	for index := 0; index < retainedViews+5; index++ {
		age := 10*time.Hour + time.Duration(index)*time.Minute
		stale = append(stale, makeView(t, parent, processViewPrefix+string(rune('a'+index)), age))
	}

	pruneStaleViews(parent)

	survivors := 0
	for _, path := range stale {
		if _, err := os.Stat(path); err == nil {
			survivors++
		}
	}
	if survivors != retainedViews {
		t.Fatalf("expected %d survivors, got %d", retainedViews, survivors)
	}
}

// 并发保护：另一个测试包刚写下的快照不能被删掉脚下。仅按个数裁剪会在并行 go test 下
// 表现为随机的文件缺失，且极难复现。
func TestPruneNeverTouchesRecentViews(t *testing.T) {
	parent := t.TempDir()
	recent := make([]string, 0, retainedViews+5)
	for index := 0; index < retainedViews+5; index++ {
		recent = append(recent, makeView(t, parent, processViewPrefix+string(rune('a'+index)), time.Minute))
	}

	pruneStaleViews(parent)

	for _, path := range recent {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("recent view %s was reclaimed: %v", path, err)
		}
	}
}

// 回收只认自己写下的两种前缀，别人放在同一个 cache 下的产物不得被波及。
func TestPruneLeavesForeignDirectoriesAlone(t *testing.T) {
	parent := t.TempDir()
	for index := 0; index < retainedViews+3; index++ {
		makeView(t, parent, processViewPrefix+string(rune('a'+index)), 10*time.Hour)
	}
	foreign := makeView(t, parent, "someone-elses-output", 10*time.Hour)

	pruneStaleViews(parent)

	if _, err := os.Stat(foreign); err != nil {
		t.Fatalf("foreign directory was reclaimed: %v", err)
	}
}

// 崩溃遗留的 go-test-* 工作目录同样要被回收：t.Cleanup 只在正常退出时跑。
func TestPruneReclaimsAbandonedWorkingRoots(t *testing.T) {
	parent := t.TempDir()
	for index := 0; index < retainedViews; index++ {
		makeView(t, parent, processViewPrefix+string(rune('a'+index)), time.Minute)
	}
	abandoned := makeView(t, parent, workingViewPrefix+"crashed", 10*time.Hour)

	pruneStaleViews(parent)

	if _, err := os.Stat(abandoned); !os.IsNotExist(err) {
		t.Fatalf("abandoned working root survived: %v", err)
	}
}
