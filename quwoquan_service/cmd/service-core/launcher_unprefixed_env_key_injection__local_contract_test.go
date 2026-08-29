// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-028
package main

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// containerLauncherBlock 把 gamma mirror 脚本按 `podman run` 切块，块内的
// `--name quwoquan_service_<svc>_1` 决定这段注入归属哪个服务。
var (
	podmanRunBoundary    = regexp.MustCompile(`podman run\b`)
	containerNameInBlock = regexp.MustCompile(
		`--name quwoquan_service_([a-z0-9-]+)_1\b`,
	)
	// 注入形态有两种：`-e KEY=value` 与 `-e KEY`（透传宿主同名变量）。
	injectedEnvKey = regexp.MustCompile(`-e ([A-Z][A-Z0-9_]*)(?:=|\s|\\|$)`)
)

// TestLauncherInjectedKeysAreNotMissingTheServicePrefix 关掉一类只在实跑该档位
// 时才显形的注入断裂：启动器把某服务的数据面键写成了无服务前缀的形态，服务按
// DEC-028 只读带前缀键，于是注入被完全忽略。
//
// 这类漂移刚在 assistant-service 上真实发生：gamma mirror 注入
// `REDIS_GENERAL_ADDR` / `REDIS_REC_ADDR`，而服务读的是
// `ASSISTANT_REDIS_GENERAL_ADDR` / `ASSISTANT_REDIS_REC_ADDR`。删掉 redis mode
// 的 schema 默认值前，这个断裂被「standalone 缺地址静默回落进程内存」掩盖：
// 服务照常起来，Redis 却是每副本一份、重启即丢的进程内存。
//
// 判据只认一种形状——注入键补上服务前缀后正好落在该服务的声明键集里。这排除了
// 全部误报：跨服务共享键（`SEARCH_ES_*`）与容器自身的键补上前缀都不在声明集里，
// 不进入判据。
func TestLauncherInjectedKeysAreNotMissingTheServicePrefix(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repository root: %v", err)
	}
	workspaceRoot := filepath.Dir(repoRoot)

	declaredByService := map[string]map[string]bool{}
	for _, service := range migratedServices() {
		keys, keysErr := service.declaredKeys()
		if keysErr != nil {
			t.Fatalf("%s declared env keys: %v", service.name, keysErr)
		}
		declared := make(map[string]bool, len(keys))
		for _, key := range keys {
			declared[key] = true
		}
		declaredByService[service.name] = declared
	}

	for _, launcher := range nonProdLaunchers() {
		if !strings.HasSuffix(launcher, ".sh") {
			continue
		}
		t.Run(filepath.Base(launcher), func(t *testing.T) {
			source, readErr := os.ReadFile(filepath.Join(workspaceRoot, launcher))
			if readErr != nil {
				t.Fatalf("read launcher: %v", readErr)
			}
			var unprefixed []string
			for service, keys := range parseContainerInjections(string(source)) {
				declared, tracked := declaredByService[service]
				if !tracked {
					continue
				}
				prefix := servicekit.DefaultEnvPrefix(service) + "_"
				for _, key := range keys {
					if declared[key] || !declared[prefix+key] {
						continue
					}
					unprefixed = append(
						unprefixed,
						service+": "+key+" (service reads "+prefix+key+")",
					)
				}
			}
			if len(unprefixed) > 0 {
				sort.Strings(unprefixed)
				t.Fatalf(
					"%s injects env keys without the owning service prefix; "+
						"the service never reads them: %v",
					launcher, unprefixed,
				)
			}
		})
	}
}

// parseContainerInjections 按 `podman run` 分块收集每个服务容器的注入键。
func parseContainerInjections(script string) map[string][]string {
	boundaries := podmanRunBoundary.FindAllStringIndex(script, -1)
	injections := map[string][]string{}
	for index, boundary := range boundaries {
		end := len(script)
		if index+1 < len(boundaries) {
			end = boundaries[index+1][0]
		}
		block := script[boundary[0]:end]
		name := containerNameInBlock.FindStringSubmatch(block)
		if name == nil {
			continue
		}
		seen := map[string]bool{}
		for _, match := range injectedEnvKey.FindAllStringSubmatch(block, -1) {
			if seen[match[1]] {
				continue
			}
			seen[match[1]] = true
			injections[name[1]] = append(injections[name[1]], match[1])
		}
	}
	return injections
}
