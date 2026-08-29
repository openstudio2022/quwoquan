// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-028
package main

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

var (
	secretRefsSectionPattern = regexp.MustCompile(`(?m)^secretRefs:\n((?:[ \t]+.*\n)*)`)
	secretRefEntryPattern    = regexp.MustCompile(`(?m)^\s+(\S+):\s*([A-Z0-9_]+)\s*$`)
	retiredKeysFuncPattern   = regexp.MustCompile(`(?s)func retiredEnvKeys\(\)[^{]*\{(.*?)\n\}`)
	quotedEnvKeyPattern      = regexp.MustCompile(`"([A-Z0-9_]+)"`)
)

// secretRefs 的右值是运行期提供该敏感配置键的 env 名——带 secretRef 的键不进
// 渲染快照（render_runtime_config.py 直接 continue），值只能由部署面注入，而
// k8s 的 envFrom.secretRef 把 secret 的 key 原样变成进程 env 名。
//
// 因此右值落在服务的 retiredEnvKeys() 里是一处 fail-closed 冲突：部署面按声明
// 注入该名字，服务却把这个名字判为退役键而拒绝启动。这类冲突在纯 compose 轨道
// 上不显形（compose 逐键显式注入新名），只在 k8s 轨道上炸，因此必须由断言而
// 不是环境实跑来发现。
func TestSecretRefEnvNamesAreNotRetiredKeys(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repo root: %v", err)
	}
	servicesDir := filepath.Join(repoRoot, "services")
	entries, err := os.ReadDir(servicesDir)
	if err != nil {
		t.Fatalf("read services dir: %v", err)
	}

	var conflicts []string
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		serviceRoot := filepath.Join(servicesDir, entry.Name())
		retired := readRetiredEnvKeys(t, serviceRoot)
		if len(retired) == 0 {
			continue
		}
		for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
			configPath := filepath.Join(serviceRoot, "environments", environment, "config.yaml")
			for configKey, envName := range readSecretRefs(t, configPath) {
				if retired[envName] {
					conflicts = append(conflicts, entry.Name()+"/"+environment+": "+
						configKey+" -> "+envName)
				}
			}
		}
	}
	sort.Strings(conflicts)

	if len(conflicts) > 0 {
		t.Fatalf(
			"secretRefs 声明的 env 名不得是服务的退役键（部署面会注入它，服务会因此拒绝启动）：\n  %s",
			strings.Join(conflicts, "\n  "),
		)
	}
}

func readRetiredEnvKeys(t *testing.T, serviceRoot string) map[string]bool {
	t.Helper()
	apiDir := filepath.Join(serviceRoot, "cmd", "api")
	entries, err := os.ReadDir(apiDir)
	if err != nil {
		return nil
	}
	retired := map[string]bool{}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(apiDir, name))
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		body := retiredKeysFuncPattern.FindSubmatch(raw)
		if body == nil {
			continue
		}
		for _, match := range quotedEnvKeyPattern.FindAllSubmatch(body[1], -1) {
			retired[string(match[1])] = true
		}
	}
	return retired
}

func readSecretRefs(t *testing.T, configPath string) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(configPath)
	if err != nil {
		return nil
	}
	section := secretRefsSectionPattern.FindSubmatch(raw)
	if section == nil {
		return nil
	}
	refs := map[string]string{}
	for _, match := range secretRefEntryPattern.FindAllSubmatch(section[1], -1) {
		refs[string(match[1])] = string(match[2])
	}
	return refs
}
