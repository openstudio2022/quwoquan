package main

import (
	"fmt"
	"strings"

	"quwoquan_service/runtime/servicekit"
)

// config 是 platform-ops-service 的声明式配置：通用段内嵌
// servicekit.BaseConfig，Postgres/Redis 场景按「声明即装配」交给骨架
// （DEC-028）。env 覆盖键一律由 envPrefix/env tag 派生为
// PLATFORM_OPS_<COMPONENT>_<FIELD>，服务侧不再有手写覆盖钩子。
//
// 三个 envAbsolute 字段是本服务读取的无前缀外部契约键，改名会撕裂本仓库以外
// 的装配面，因此精确保留原名：
//   - REPO_ROOT 是全仓通用的仓库/事实树根约定（Makefile、build/Dockerfile、
//     compose 只读挂载、大量 ops 脚本共用同一键名）。
//   - RELEASE_MANIFEST_DIGEST 是发布包身份，全体受管服务与 config sync
//     ACK 证据共用同一键名（servicekit.RegisterConfigSync 也读它）。
//   - ALERT_INGEST_TOKEN 是与 Alertmanager 监控栈对侧共享的机器凭据键，
//     由 quwoquan_ops/observability/monitoring 与 prod access-isolation
//     清单同名声明。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Postgres servicekit.PostgresConfig `yaml:"postgres"`

	Redis struct {
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"GENERAL"`
	} `yaml:"redis" envPrefix:"REDIS"`

	// ConfigAck 是发布编排使用的 config ACK 收敛判据。它由 rollout 渲染器
	// 按本次发布的成员清单注入，不进入环境配置快照。
	ConfigAck struct {
		RequiredInstances []string `yaml:"required_instances" env:"REQUIRED_INSTANCES"`
		MaxAgeSeconds     int      `yaml:"max_age_seconds" env:"MAX_AGE_SECONDS"`
	} `yaml:"config_ack" envPrefix:"CONFIG_ACK"`

	// RepoRoot 必填：拓扑与配置快照只读源就在这棵树上。迁移前它在缺注入时
	// 由 cwd 向上探测并最终回落到工作目录，那会让「事实树未挂载」伪装成一个
	// 存在但为空的根，把缺席变成运行期 500。
	RepoRoot              string `yaml:"-" envAbsolute:"REPO_ROOT" required:"true"`
	ReleaseManifestDigest string `yaml:"-" envAbsolute:"RELEASE_MANIFEST_DIGEST"`
	AlertIngestToken      string `yaml:"-" envAbsolute:"ALERT_INGEST_TOKEN"`
}

const (
	// defaultConfigAckMaxAgeSeconds 是未注入 max_age_seconds 时的 ACK 新鲜度
	// 窗口，与迁移前的默认值一致。
	defaultConfigAckMaxAgeSeconds = 120
	minConfigAckMaxAgeSeconds     = 30
	maxConfigAckMaxAgeSeconds     = 600
)

// retiredEnvKeys 是迁移到声明式装配时退役的无前缀键。它们在本服务的进程
// 环境中出现即启动失败：POSTGRES_DSN 是多个服务共用的无前缀键名，同机共享
// 环境时会把本服务连到别人的库；CONFIG_ACK_* 已收敛到服务前缀形态。
func retiredEnvKeys() []string {
	return []string{
		"POSTGRES_DSN",
		"CONFIG_ACK_REQUIRED_INSTANCES",
		"CONFIG_ACK_MAX_AGE_SECONDS",
	}
}

// validatePlatformOpsConfig 施加领域配置下界。它在 required 校验之后、任何
// 外部连接之前执行，因此非法配置不会产生副作用。
func validatePlatformOpsConfig(cfg *config) error {
	// 未被环境装配替换的 ${VAR} 占位符既不是有效 DSN 也不是缺席；直接连接
	// 会把注入缺口伪装成连接错误。
	if strings.HasPrefix(strings.TrimSpace(cfg.Postgres.DSN), "${") {
		return fmt.Errorf(
			"postgres.dsn still holds an unrendered placeholder: %s", cfg.Postgres.DSN,
		)
	}
	// general scene 承载 ConfigInstanceReport outbox 的 typed event 总线，因此
	// 本服务不接受 memory 声明：跨实例事件投递会变成单进程内存态。
	mode, err := cfg.Redis.General.DeclaredMode()
	if err != nil {
		return fmt.Errorf("redis.general %w", err)
	}
	if mode == servicekit.RedisModeMemory {
		return fmt.Errorf(
			"redis.general must declare a real topology: this service's " +
				"config report outbox requires cross-instance visibility",
		)
	}
	if seconds := cfg.ConfigAck.MaxAgeSeconds; seconds != 0 &&
		(seconds < minConfigAckMaxAgeSeconds || seconds > maxConfigAckMaxAgeSeconds) {
		return fmt.Errorf(
			"config_ack.max_age_seconds must be within %d..%d, got %d",
			minConfigAckMaxAgeSeconds, maxConfigAckMaxAgeSeconds, seconds,
		)
	}
	// 生产的实例报告与 ACK 收敛判据都以发布包 digest 为锚；缺它则收敛判据
	// 无法证明「当前发布包已下发」。
	if cfg.Environment == "prod" && !isCanonicalSHA256(cfg.ReleaseManifestDigest) {
		return fmt.Errorf("RELEASE_MANIFEST_DIGEST is required in prod")
	}
	return nil
}

// configAckMaxAgeSeconds 解析生效的 ACK 新鲜度窗口。缺席取默认值；越界值
// 已在配置校验阶段 fail-closed，不在此处静默夹取。
func (cfg *config) configAckMaxAgeSeconds() int {
	if cfg.ConfigAck.MaxAgeSeconds == 0 {
		return defaultConfigAckMaxAgeSeconds
	}
	return cfg.ConfigAck.MaxAgeSeconds
}
