package main

import (
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/runtime/servicekit"
	apiedge "quwoquan_service/services/api-edge/cmd/api"
	assistant "quwoquan_service/services/assistant-service/cmd/api"
	chat "quwoquan_service/services/chat-service/cmd/api"
	circle "quwoquan_service/services/circle-service/cmd/api"
	content "quwoquan_service/services/content-service/cmd/api"
	entity "quwoquan_service/services/entity-service/cmd/api"
	integration "quwoquan_service/services/integration-service/cmd/api"
	notification "quwoquan_service/services/notification-service/cmd/api"
	search "quwoquan_service/services/search-service/cmd/api"
	tag "quwoquan_service/services/tag-service/cmd/api"
	user "quwoquan_service/services/user-service/cmd/api"
)

// composeEnvKeyPattern 抓取 compose service.environment 下的键。缩进固定为
// 六个空格是本仓库 compose 的既有形态（services -> <name> -> environment）。
var composeEnvKeyPattern = regexp.MustCompile(`(?m)^      ([A-Z][A-Z0-9_]*):`)

// migratedService 是一个已迁移到声明式装配的 service-core 模块。
type migratedService struct {
	name         string
	declaredKeys func() ([]string, error)
}

// migratedServices 是对账覆盖面。迁移一个服务就把它加进来，未迁移的服务仍在
// 手写 env 覆盖，没有可对账的声明键集。
func migratedServices() []migratedService {
	return []migratedService{
		{"api-edge", apiedge.DeclaredEnvKeys},
		{"assistant-service", assistant.DeclaredEnvKeys},
		{"chat-service", chat.DeclaredEnvKeys},
		{"circle-service", circle.DeclaredEnvKeys},
		{"content-service", content.DeclaredEnvKeys},
		{"entity-service", entity.DeclaredEnvKeys},
		{"integration-service", integration.DeclaredEnvKeys},
		{"notification-service", notification.DeclaredEnvKeys},
		{"search-service", search.DeclaredEnvKeys},
		{"tag-service", tag.DeclaredEnvKeys},
		{"user-service", user.DeclaredEnvKeys},
	}
}

// TestComposeInjectedKeysHaveDeclaredConsumers 关掉一类静默失效：部署面注入了
// 一个服务前缀的 env 键，而服务侧没有任何消费者，于是注入被忽略、服务带着
// 渲染快照里的旧值起来（迁移期真实出现过：tag-service 的 REDIS_ADDR）。
//
// 合法消费轨道有三条：声明式运行配置派生的覆盖键、服务 contracts 里
// adapterContracts 声明的 provider endpoint/secret 键（含尚未选中的备选
// adapter）、以及仓库内 Go 源码的字面量引用（如发布工具）。三条都无即判漂移。
func TestComposeInjectedKeysHaveDeclaredConsumers(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repository root: %v", err)
	}
	for _, service := range migratedServices() {
		t.Run(service.name, func(t *testing.T) {
			keys, err := service.declaredKeys()
			if err != nil {
				t.Fatalf("declared env keys: %v", err)
			}
			declared := make(map[string]bool, len(keys))
			for _, key := range keys {
				declared[key] = true
			}
			serviceRoot := filepath.Join(repoRoot, "services", service.name)
			sources := readServiceDeclarationSources(t, serviceRoot)
			prefix := servicekit.DefaultEnvPrefix(service.name) + "_"
			composeSource, err := os.ReadFile(
				filepath.Join(serviceRoot, "deploy", "compose.yaml"),
			)
			if err != nil {
				t.Fatalf("read compose: %v", err)
			}
			var orphaned []string
			for _, match := range composeEnvKeyPattern.FindAllStringSubmatch(
				string(composeSource), -1,
			) {
				key := match[1]
				if !strings.HasPrefix(key, prefix) || declared[key] {
					continue
				}
				if hasConsumerReference(sources, key) {
					continue
				}
				orphaned = append(orphaned, key)
			}
			if len(orphaned) > 0 {
				sort.Strings(orphaned)
				t.Fatalf(
					"compose injects %s keys with no consumer in the service: %v",
					prefix, orphaned,
				)
			}
		})
	}
}

// dataPlaneEnvKeyTokens 标出「指向一个具体存储实例」的 env 键。这类键一旦被
// 同进程的两个模块共享，两个模块就被迫连同一个实例，且任何一方想换实例都会
// 悄悄改变另一方——所以它们必须带服务前缀。
var dataPlaneEnvKeyTokens = []string{"MONGO", "POSTGRES", "REDIS", "ELASTIC", "_ES_"}

// TestDataPlaneEnvKeysAreNotSharedAcrossModules 关掉单进程 service-core 特有的
// 串味风险：多个模块在同一个进程里读同一份 os.Environ，共享一个无服务前缀的
// 数据面键就等于共享一个存储实例，且这种耦合不出现在任何配置文件里。
func TestDataPlaneEnvKeysAreNotSharedAcrossModules(t *testing.T) {
	owners := map[string][]string{}
	for _, service := range migratedServices() {
		keys, err := service.declaredKeys()
		if err != nil {
			t.Fatalf("%s declared env keys: %v", service.name, err)
		}
		prefix := servicekit.DefaultEnvPrefix(service.name) + "_"
		for _, key := range keys {
			if strings.HasPrefix(key, prefix) || !isDataPlaneEnvKey(key) {
				continue
			}
			owners[key] = append(owners[key], service.name)
		}
	}
	var shared []string
	for key, services := range owners {
		if len(services) > 1 {
			sort.Strings(services)
			shared = append(shared, key+" <- "+strings.Join(services, ","))
		}
	}
	if len(shared) > 0 {
		sort.Strings(shared)
		t.Fatalf(
			"data plane env keys are shared by multiple service-core modules: %v",
			shared,
		)
	}
}

// TestDataPlaneEnvKeysCarryServicePrefix 把「不共享」升级为「不可共享」：只要
// 数据面键带服务前缀，跨模块串味就在命名层被排除，不必等到两个模块恰好都声明
// 了同一个无前缀键才发现。共享键出现在单模块时前一个测试是绿的，但它已经埋下
// 了下一个模块迁移时的冲突。
func TestDataPlaneEnvKeysCarryServicePrefix(t *testing.T) {
	for _, service := range migratedServices() {
		t.Run(service.name, func(t *testing.T) {
			keys, err := service.declaredKeys()
			if err != nil {
				t.Fatalf("declared env keys: %v", err)
			}
			prefix := servicekit.DefaultEnvPrefix(service.name) + "_"
			var unprefixed []string
			for _, key := range keys {
				if strings.HasPrefix(key, prefix) || !isDataPlaneEnvKey(key) {
					continue
				}
				unprefixed = append(unprefixed, key)
			}
			if len(unprefixed) > 0 {
				sort.Strings(unprefixed)
				t.Fatalf(
					"data plane env keys must carry the %s prefix, got %v",
					prefix, unprefixed,
				)
			}
		})
	}
}

func isDataPlaneEnvKey(key string) bool {
	for _, token := range dataPlaneEnvKeyTokens {
		if strings.Contains(key, token) {
			return true
		}
	}
	return false
}

// hasConsumerReference 判定 key 是否以完整标识符出现在声明源里，避免
// X_ADDR 被 X_ADDRS 的出现误判为已消费。
// prodPlaneInjectionPattern 抓取 prod plane 渲染脚本里针对单个服务的 env 注入。
var (
	// 服务分块有两种写法：`if name == "x":` 与带条件前缀的
	// `if instance == "prevalidate" and name == "x":`。
	prodPlaneServicePattern = regexp.MustCompile(
		`(?m)^        if (?:[^\n]*and )?name == "([a-z0-9-]+)":$`,
	)
	prodPlaneKeyPattern = regexp.MustCompile(`environment\["([A-Z][A-Z0-9_]*)"\]`)
	prodPlaneDictKey    = regexp.MustCompile(`(?m)^\s+"([A-Z][A-Z0-9_]*)":`)
)

// TestProdPlaneInjectedKeysHaveDeclaredConsumers 把同一条对账扩到 prod plane：
// 渲染脚本按服务注入的 env 键，若服务侧无任何消费者，prod 就会带着渲染快照里的
// 默认值起来——比 compose 更难发现，因为 prod 没有人肉观察窗口。
func TestProdPlaneInjectedKeysHaveDeclaredConsumers(t *testing.T) {
	repoRoot, err := filepath.Abs("../..")
	if err != nil {
		t.Fatalf("resolve repository root: %v", err)
	}
	renderScript, err := os.ReadFile(filepath.Join(
		repoRoot, "..", "quwoquan_ops", "cli", "prod", "render_prod_plane_stack.py",
	))
	if err != nil {
		t.Fatalf("read prod plane render script: %v", err)
	}
	injections := parseProdPlaneInjections(string(renderScript))
	for _, service := range migratedServices() {
		t.Run(service.name, func(t *testing.T) {
			keys := injections[service.name]
			if len(keys) == 0 {
				// 无 prod plane 注入即没有该维度的待对账对象；不是未执行测试。
				return
			}
			declaredKeys, err := service.declaredKeys()
			if err != nil {
				t.Fatalf("declared env keys: %v", err)
			}
			declared := make(map[string]bool, len(declaredKeys))
			for _, key := range declaredKeys {
				declared[key] = true
			}
			serviceRoot := filepath.Join(repoRoot, "services", service.name)
			sources := readServiceDeclarationSources(t, serviceRoot)
			var orphaned []string
			for _, key := range keys {
				if declared[key] || hasConsumerReference(sources, key) {
					continue
				}
				orphaned = append(orphaned, key)
			}
			if len(orphaned) > 0 {
				sort.Strings(orphaned)
				t.Fatalf(
					"prod plane injects keys with no consumer in %s: %v",
					service.name, orphaned,
				)
			}
		})
	}
}

// parseProdPlaneInjections 按 `if name == "<service>":` 分块收集注入键，块内
// 既覆盖 environment["K"] 赋值，也覆盖 environment.update({...}) 的字典键。
func parseProdPlaneInjections(script string) map[string][]string {
	matches := prodPlaneServicePattern.FindAllStringSubmatchIndex(script, -1)
	injections := map[string][]string{}
	for index, match := range matches {
		name := script[match[2]:match[3]]
		end := len(script)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		block := script[match[1]:end]
		seen := map[string]bool{}
		for _, pattern := range []*regexp.Regexp{prodPlaneKeyPattern, prodPlaneDictKey} {
			for _, keyMatch := range pattern.FindAllStringSubmatch(block, -1) {
				if seen[keyMatch[1]] {
					continue
				}
				seen[keyMatch[1]] = true
				injections[name] = append(injections[name], keyMatch[1])
			}
		}
	}
	return injections
}

func hasConsumerReference(sources, key string) bool {
	offset := 0
	for {
		index := strings.Index(sources[offset:], key)
		if index < 0 {
			return false
		}
		end := offset + index + len(key)
		if end >= len(sources) || !isEnvKeyRune(sources[end]) {
			return true
		}
		offset = end
	}
}

func isEnvKeyRune(char byte) bool {
	return char == '_' || (char >= 'A' && char <= 'Z') || (char >= '0' && char <= '9')
}

// readServiceDeclarationSources 把一个服务的非测试 Go 源码与 contracts 声明
// 拼成单串，用于判定某个 env 键是否存在消费者。
func readServiceDeclarationSources(t *testing.T, serviceRoot string) string {
	t.Helper()
	var builder strings.Builder
	err := filepath.WalkDir(serviceRoot, func(
		path string, entry fs.DirEntry, err error,
	) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		isSource := strings.HasSuffix(path, ".go") &&
			!strings.HasSuffix(path, "_test.go")
		isContract := strings.HasSuffix(path, ".yaml") &&
			strings.Contains(path, string(os.PathSeparator)+"contracts"+string(os.PathSeparator))
		if !isSource && !isContract {
			return nil
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		builder.Write(content)
		return nil
	})
	if err != nil {
		t.Fatalf("walk %s: %v", serviceRoot, err)
	}
	return builder.String()
}
