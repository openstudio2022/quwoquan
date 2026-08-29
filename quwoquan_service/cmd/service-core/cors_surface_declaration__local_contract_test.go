// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-028
package main

import (
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
)

// corsBearingServices 是迁移前实际挂载 rthttp.WithCORS 的服务全集，逐个从
// 迁移前的 cmd/api/main.go 核对得出。
//
// 骨架曾无条件挂载 CORS，等于给其余每个服务凭空加了一个 OPTIONS → 204 的
// 未认证面（不过观测、不过 operation guard、不过共享准入、不计量）。这条
// 断言把跨域面锁回真实需要它的服务：新增一个声明必须先证明该服务的入站面
// 确实接受浏览器跨域直连。
func corsBearingServices() map[string]string {
	return map[string]string{
		"chat-service":        "群头像等媒体面由浏览器直连",
		"product-ops-service": "运营台是浏览器直连入口",
		"tag-service":         "迁移前既有跨域面",
	}
}

func TestCORSSurfaceMatchesDeclaredBrowserEntrypoints(t *testing.T) {
	servicesDir := filepath.Join(repositoryServiceRoot(t), "services")
	entries, err := os.ReadDir(servicesDir)
	if err != nil {
		t.Fatalf("read services dir: %v", err)
	}

	expected := corsBearingServices()
	var actual []string
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		bootstrapPath := filepath.Join(servicesDir, entry.Name(), "cmd", "api", "bootstrap.go")
		raw, err := os.ReadFile(bootstrapPath)
		if err != nil {
			// 尚未迁移到声明式骨架的服务没有 bootstrap.go，不在本断言范围内。
			continue
		}
		if strings.Contains(string(raw), "CORS:") {
			actual = append(actual, entry.Name())
		}
	}
	sort.Strings(actual)

	var expectedNames []string
	for name := range expected {
		expectedNames = append(expectedNames, name)
	}
	sort.Strings(expectedNames)

	if strings.Join(actual, ",") != strings.Join(expectedNames, ",") {
		t.Fatalf(
			"挂载 CORS 的服务集合必须与已声明的浏览器直连入口一致：\n实际 %v\n期望 %v\n"+
				"新增跨域面前必须先在 corsBearingServices 里给出该服务接受浏览器跨域直连的理由",
			actual, expectedNames,
		)
	}
}

func repositoryServiceRoot(t *testing.T) string {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(source), "../../"))
}
