package servicekit

import (
	"fmt"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
)

// RedisSceneConfig 是各服务配置快照中一个 Redis scene 的统一 YAML 结构。
// env tag 是相对后缀，完整键由服务 config struct 的 envPrefix 链拼出
// （如 TAG_REDIS_GENERAL_MODE、CIRCLE_REDIS_ADDR）；Pool 属快照调优面，
// 不接受 env 覆盖。
type RedisSceneConfig struct {
	Mode     string   `yaml:"mode" env:"MODE"`
	Addr     string   `yaml:"addr" env:"ADDR"`
	Addrs    []string `yaml:"addrs" env:"ADDRS"`
	Password string   `yaml:"password" env:"PASSWORD"`
	DB       int      `yaml:"db" env:"DB"`
	TLS      bool     `yaml:"tls" env:"TLS"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

// Redis scene 的合法 mode 闭集。取值就是拓扑名本身，读到即知语义，不需要二次
// 翻译，也不存在「某个值顺带表达了别的意思」。
const (
	RedisModeMemory     = "memory"
	RedisModeStandalone = "standalone"
	RedisModeCluster    = "cluster"
)

// IsUndeclared 判定这一段 scene 配置整段缺席——没有任何一个字段被声明过。
//
// 「整段缺席即复用另一个 scene 的声明」是本仓库唯一合法的 scene 复用规则：规则
// 写在装配处、只有一条、复用的是完整一段，读者能一眼看出这个 scene 的每个字段
// 都来自哪里。字段级回落不合法——它会把 realtime 的 mode 和 general 的地址拼成
// 一份没人声明过的配置，出问题时没有任何一个文件能解释生效值。
//
// 与 DeclaredMode 的分工：本方法只回答「有没有人声明过这一段」，不回答「声明得
// 对不对」。复用后的那一段仍要过 DeclaredMode 的校验。
func (config RedisSceneConfig) IsUndeclared() bool {
	return strings.TrimSpace(config.Mode) == "" &&
		strings.TrimSpace(config.Addr) == "" &&
		len(config.Addrs) == 0 &&
		config.Password == "" &&
		config.DB == 0 &&
		!config.TLS &&
		config.Pool == RedisSceneConfig{}.Pool
}

// DeclaredMode 返回归一化后的声明 mode，并在声明缺失、取值非法或声明与地址
// 不一致时判否。
//
// 运行模式只由 mode 表达，不由地址在场与否推断：地址为空既可能是「本环境不接
// 真实 Redis」也可能是「漏了地址注入」，两者后果相反——静默按前者处理会让多
// 副本各自持有一份不共享、重启即丢的「Redis」，而幂等键、分布式锁与会话都建立
// 在跨副本可见的前提上，且这类失效在运行期不产生任何信号。因此「不接真实
// Redis」必须由 mode: memory 显式声明，那是唯一合法的关停路径。
//
// mode 的四层声明位是全局默认（quwoquan_ops/environments/config-defaults.yaml）、
// 环境默认、服务 environments/<env>/config.yaml、服务 config/schema.yaml 的
// default，取值优先级从高到低相反，任一生效值都能指回一处写下它的文件。
//
// 判否文本描述缺的那处声明或注入键，不描述症状：触发它的现实场景是环境装配注入
// 了单点 addr 却没覆盖 cluster 声明，读者需要知道该改哪个文件。
func (config RedisSceneConfig) DeclaredMode() (string, error) {
	declared := strings.ToLower(strings.TrimSpace(config.Mode))
	addr := strings.TrimSpace(config.Addr)
	switch declared {
	case "":
		return "", fmt.Errorf(
			"has no mode declared; declare mode as one of %s/%s/%s in the "+
				"service environment config, an environment-wide "+
				"config-defaults.yaml, or the global config-defaults.yaml",
			RedisModeMemory, RedisModeStandalone, RedisModeCluster,
		)
	case RedisModeMemory:
		// memory 与地址同时在场是两处声明互相矛盾，判否比挑一处生效更安全：
		// 挑地址会让声明的关停失效，挑 memory 会让注入的地址静默失效。
		if addr != "" || len(config.Addrs) > 0 {
			return declared, fmt.Errorf(
				"declares mode=%s but an address is also injected "+
					"(addr=%q, addrs=%d); drop the address injection, or "+
					"declare the topology that address belongs to",
				RedisModeMemory, config.Addr, len(config.Addrs),
			)
		}
		return RedisModeMemory, nil
	case RedisModeStandalone:
		if addr == "" {
			return declared, fmt.Errorf(
				"declares mode=%s but no addr is injected; inject the addr, "+
					"or declare mode=%s to mean this scene is not backed by "+
					"Redis in this environment",
				RedisModeStandalone, RedisModeMemory,
			)
		}
		if len(config.Addrs) > 0 {
			return declared, fmt.Errorf(
				"declares mode=%s but %d cluster addrs are also injected; "+
					"drop the addrs, or declare mode=%s",
				RedisModeStandalone, len(config.Addrs), RedisModeCluster,
			)
		}
		return RedisModeStandalone, nil
	case RedisModeCluster:
		if len(config.Addrs) == 0 {
			if addr != "" {
				return declared, fmt.Errorf(
					"declares mode=%s but only a single addr (%s) is "+
						"injected; inject the cluster addrs, or declare "+
						"mode=%s in this environment",
					RedisModeCluster, addr, RedisModeStandalone,
				)
			}
			return declared, fmt.Errorf(
				"declares mode=%s but no addrs are injected; inject the "+
					"cluster addrs, or declare mode=%s to mean this scene is "+
					"not backed by Redis in this environment",
				RedisModeCluster, RedisModeMemory,
			)
		}
		if addr != "" {
			return declared, fmt.Errorf(
				"declares mode=%s with cluster addrs but a standalone addr "+
					"(%s) is also injected; drop one of the two address "+
					"injections",
				RedisModeCluster, addr,
			)
		}
		return RedisModeCluster, nil
	default:
		return declared, fmt.Errorf(
			"declares unsupported mode %q; declare one of %s/%s/%s",
			config.Mode, RedisModeMemory, RedisModeStandalone, RedisModeCluster,
		)
	}
}

// SceneConfig 解析出运行时 scene 配置。错误随返回值一起交出，调用方不得丢弃：
// 吞掉它会让装配期判否退化成注释里的承诺。
func (config RedisSceneConfig) SceneConfig() (rtredis.SceneConfig, error) {
	mode, err := config.DeclaredMode()
	return rtredis.SceneConfig{
		Mode:           mode,
		Addr:           config.Addr,
		Addrs:          config.Addrs,
		Password:       config.Password,
		DB:             config.DB,
		TLS:            config.TLS,
		PoolSize:       config.Pool.Size,
		MinIdleConns:   config.Pool.MinIdle,
		ReadTimeoutMs:  config.Pool.ReadTimeoutMs,
		WriteTimeoutMs: config.Pool.WriteTimeoutMs,
		DialTimeoutMs:  config.Pool.DialTimeoutMs,
	}, err
}

// NewRedisRouter 以 codegen 的 scene 名/前缀路由为基线（全部 memory）装配
// Redis 场景路由器，用服务声明的 scene 配置覆盖，并返回声明 scene 的解析后
// mode 供消息传输 preflight 使用。
func NewRedisRouter(
	scenes map[string]RedisSceneConfig,
) (*rtredis.Router, map[string]string, error) {
	if len(scenes) == 0 {
		return nil, nil, fmt.Errorf("at least one Redis scene is required")
	}
	routerConfig := rtredis.DefaultRouterConfig()
	sceneModes := make(map[string]string, len(scenes))
	for name, sceneConfig := range scenes {
		sceneName := strings.TrimSpace(name)
		if sceneName == "" {
			return nil, nil, fmt.Errorf("Redis scene name must not be empty")
		}
		// 逻辑库编号只有非负值有意义；负数是注入错误，静默取 0 会让本 scene
		// 连到别人的 db。
		if sceneConfig.DB < 0 {
			return nil, nil, fmt.Errorf(
				"Redis scene %s db must be a non-negative integer, got %d",
				sceneName, sceneConfig.DB,
			)
		}
		resolved, err := sceneConfig.SceneConfig()
		if err != nil {
			return nil, nil, fmt.Errorf("Redis scene %s %w", sceneName, err)
		}
		routerConfig.Scenes[sceneName] = resolved
		sceneModes[sceneName] = resolved.Mode
	}
	router, err := platformredis.NewRouter(routerConfig)
	if err != nil {
		return nil, nil, err
	}
	return router, sceneModes, nil
}
