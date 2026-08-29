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

// nonProdLaunchers 是四环境里除服务 compose 与 prod 渲染器之外的进程启动器。
// 那两处已由 TestComposeInjectedKeysHaveDeclaredConsumers 与
// TestProdPlaneInjectedKeysHaveDeclaredConsumers 对账，这里补上剩下的三个：
// 它们过去是对账盲区，而盲区里的漂移不会被任何静态检查看见——启动器与断言
// 测试互相自洽，只是都与服务声明不一致，失效要到实跑该档位时才显形。
func nonProdLaunchers() []string {
	return []string{
		filepath.Join("quwoquan_app", "scripts", "gamma", "start_local_gamma_mirror.sh"),
		filepath.Join("quwoquan_app", "scripts", "tools", "device", "beta_manual_app.sh"),
		filepath.Join("quwoquan_ops", "cli", "alpha", "content_release_runtime.py"),
	}
}

// retiredEnvKeysBlock 匹配服务侧 `retiredEnvKeys()` 的函数体。退役键集是包私有
// 的，这里按字面量取而不是导出它：字面量就是真相源，导出只为让测试可见会让
// 可见性反映测试需要而不是领域边界。
var (
	retiredEnvKeysBlock = regexp.MustCompile(
		`(?s)func [Rr]etiredEnvKeys\(\) \[\]string \{(.*?)\n\}`,
	)
	envKeyLiteral = regexp.MustCompile(`"([A-Z][A-Z0-9_]*)"`)
)

// TestLaunchersDoNotInjectRetiredEnvKeys 关掉一类运行期断裂：服务把一个 env 键
// 声明为退役（注入即 fail-closed 启动失败），而某个环境启动器仍在注入它。
//
// 这类漂移刚在 entity-service 上真实发生：scene 化后 `ENTITY_REDIS_ADDR` 退役，
// 但 gamma mirror、beta 手工脚本与 alpha content release runtime 三处仍注入它，
// 且第四处是断言前者的测试——四处互相自洽，测试全绿，服务却会在这些档位启动
// 即被拒。
//
// 判据取「退役键出现在启动器文本里」而不是「注入给哪个容器」，这只对**带服务
// 前缀**的退役键成立：DEC-028 要求数据面键带服务前缀，这类键名本身唯一确定
// 归属。无前缀的旧键（`MONGODB_URI`、`POSTGRES_DSN` 等）被排除在判据外——同一
// 个键名在启动器里可能是注入给尚未迁移的服务或数据容器自身，凭键名分不出注入
// 对象，要判它们需要按容器块解析启动器，那是另一条判据。
func TestLaunchersDoNotInjectRetiredEnvKeys(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repository root: %v", err)
	}
	workspaceRoot := filepath.Dir(repoRoot)

	retired := collectRetiredEnvKeys(t, repoRoot)
	if len(retired) == 0 {
		t.Fatal("no retired env keys found: the collector no longer matches the source shape")
	}

	for _, launcher := range nonProdLaunchers() {
		t.Run(filepath.Base(launcher), func(t *testing.T) {
			source, err := os.ReadFile(filepath.Join(workspaceRoot, launcher))
			if err != nil {
				t.Fatalf("read launcher: %v", err)
			}
			text := string(source)
			var injected []string
			for key, owner := range retired {
				if regexp.MustCompile(`\b` + key + `\b`).MatchString(text) {
					injected = append(injected, key+" (retired by "+owner+")")
				}
			}
			if len(injected) > 0 {
				sort.Strings(injected)
				t.Fatalf(
					"%s injects env keys the owning service has retired; "+
						"the service fails closed on them at startup: %v",
					launcher, injected,
				)
			}
		})
	}
}

// collectRetiredEnvKeys 收集全部服务声明的退役键，映射到声明它的服务名。
func collectRetiredEnvKeys(t *testing.T, repoRoot string) map[string]string {
	t.Helper()
	retired := map[string]string{}
	for _, root := range []string{
		filepath.Join(repoRoot, "services"),
		filepath.Join(repoRoot, "control-plane"),
	} {
		entries, err := os.ReadDir(root)
		if err != nil {
			t.Fatalf("read %s: %v", root, err)
		}
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			serviceName := entry.Name()
			apiDir := filepath.Join(root, serviceName, "cmd", "api")
			files, err := os.ReadDir(apiDir)
			if err != nil {
				continue
			}
			for _, file := range files {
				if !strings.HasSuffix(file.Name(), ".go") ||
					strings.HasSuffix(file.Name(), "_test.go") {
					continue
				}
				source, err := os.ReadFile(filepath.Join(apiDir, file.Name()))
				if err != nil {
					t.Fatalf("read %s: %v", file.Name(), err)
				}
				block := retiredEnvKeysBlock.FindStringSubmatch(string(source))
				if block == nil {
					continue
				}
				prefix := servicekit.DefaultEnvPrefix(serviceName) + "_"
				for _, match := range envKeyLiteral.FindAllStringSubmatch(block[1], -1) {
					if !strings.HasPrefix(match[1], prefix) {
						continue
					}
					retired[match[1]] = serviceName
				}
			}
		}
	}
	return retired
}
