package main

import (
	"sort"
	"strings"
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// TestDeclaredEnvKeysCoverHandwrittenOverrides 锁定声明式配置派生的 env 覆盖
// 键集与迁移前手写 applyPlatformEnvOverrides / os.Getenv 直读的键集等价：
// 迁移前处理过的每个键都有唯一后继，被重命名的键彻底退役而不是并存双读。
func TestDeclaredEnvKeysCoverHandwrittenOverrides(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("declared env keys: %v", err)
	}
	declared := map[string]bool{}
	for _, key := range keys {
		declared[key] = true
	}

	// successors 左侧是迁移前被读取的键，右侧是迁移后的唯一声明键。
	successors := map[string]string{
		// 监听地址：键名不变。
		"PLATFORM_OPS_SERVICE_ADDR": "PLATFORM_OPS_SERVICE_ADDR",
		// Postgres DSN：无前缀键退役，收敛到服务前缀。
		"POSTGRES_DSN": "PLATFORM_OPS_POSTGRES_DSN",
		// ConfigInstanceReport outbox 的 typed event 总线：键名不变。
		"PLATFORM_OPS_REDIS_GENERAL_ADDR": "PLATFORM_OPS_REDIS_GENERAL_ADDR",
		// 发布收敛判据：收敛到服务前缀。
		"CONFIG_ACK_REQUIRED_INSTANCES": "PLATFORM_OPS_CONFIG_ACK_REQUIRED_INSTANCES",
		"CONFIG_ACK_MAX_AGE_SECONDS":    "PLATFORM_OPS_CONFIG_ACK_MAX_AGE_SECONDS",
		// 外部契约键：原名保留（见 config 的 envAbsolute 注释）。
		"REPO_ROOT":               "REPO_ROOT",
		"RELEASE_MANIFEST_DIGEST": "RELEASE_MANIFEST_DIGEST",
		"ALERT_INGEST_TOKEN":      "ALERT_INGEST_TOKEN",
		"PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_KEY_ID":             "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_KEY_ID",
		"PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_FILE":   "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_FILE",
		"PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_BASE64": "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_BASE64",
		"PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_TEST_KEY":           "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_TEST_KEY",
		"PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_WEBHOOK_SECRET":      "PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_WEBHOOK_SECRET",
		"PLATFORM_OPS_HUMAN_AUTHORITY_ROLE_MAPPINGS":              "PLATFORM_OPS_HUMAN_AUTHORITY_ROLE_MAPPINGS",
		"PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_MAPPINGS":            "PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_MAPPINGS",
	}
	for legacy, successor := range successors {
		if !declared[successor] {
			t.Fatalf("declared env keys missing %s (successor of %s)", successor, legacy)
		}
		if legacy != successor && declared[legacy] {
			t.Fatalf("renamed env key %s must not stay declared alongside %s", legacy, successor)
		}
	}

	// 退役键在进程环境出现即启动失败；它们不得同时还是声明键。
	for _, retired := range retiredEnvKeys() {
		if declared[retired] {
			t.Fatalf("retired env key %s is still declared", retired)
		}
		if successor, renamed := successors[retired]; !renamed || successor == retired {
			t.Fatalf("retired env key %s has no declared successor", retired)
		}
	}

	// 声明键必须全部落在服务前缀下，或者是上表显式登记的外部契约键。
	for _, key := range keys {
		if strings.HasPrefix(key, "PLATFORM_OPS_") {
			continue
		}
		if successor, ok := successors[key]; ok && successor == key {
			continue
		}
		t.Fatalf(
			"env key %s is neither service-prefixed nor a registered absolute contract key",
			key,
		)
	}
}

// TestDeclaredEnvKeysAreUnique 锁定不存在两个字段抢同一个 env 键：重复声明会
// 让「哪个字段生效」取决于遍历顺序。
func TestDeclaredEnvKeysAreUnique(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("declared env keys: %v", err)
	}
	sorted := append([]string(nil), keys...)
	sort.Strings(sorted)
	for index := 1; index < len(sorted); index++ {
		if sorted[index] == sorted[index-1] {
			t.Fatalf("duplicate declared env key %s", sorted[index])
		}
	}
}

// TestValidatePlatformOpsConfigRejectsUnrenderedPlaceholder 锁定未渲染的
// ${VAR} 占位符被当成注入缺口拒收，而不是清空后靠 required 报一个失真的
// 「缺配置」，更不能拿去当 DSN 连接。
func TestValidatePlatformOpsConfigRejectsUnrenderedPlaceholder(t *testing.T) {
	cfg := validPlatformOpsConfig()
	cfg.Postgres.DSN = "${QWQ_POSTGRES_DSN}"
	err := validatePlatformOpsConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "unrendered placeholder") {
		t.Fatalf("expected unrendered postgres.dsn rejection, got %v", err)
	}
}

// TestValidatePlatformOpsConfigRequiresRealRedisScene 锁定 fail-closed：
// general scene 承载 ConfigInstanceReport 的跨实例事件投递，因此三种形态都必须
// 判否——声明 standalone 却缺地址（注入缺陷）、显式声明 memory（本服务不接受）、
// 以及完全没声明 mode。
func TestValidatePlatformOpsConfigRequiresRealRedisScene(t *testing.T) {
	cases := map[string]func(*config){
		"standalone without addr": func(cfg *config) {
			cfg.Redis.General.Addr = ""
		},
		"explicit memory": func(cfg *config) {
			cfg.Redis.General.Mode = servicekit.RedisModeMemory
			cfg.Redis.General.Addr = ""
		},
		"no mode declared": func(cfg *config) {
			cfg.Redis.General.Mode = ""
		},
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := validPlatformOpsConfig()
			mutate(cfg)
			err := validatePlatformOpsConfig(cfg)
			if err == nil || !strings.Contains(err.Error(), "redis.general") {
				t.Fatalf("expected redis.general requirement, got %v", err)
			}
		})
	}
}

// TestValidatePlatformOpsConfigBoundsConfigAckMaxAge 锁定 ACK 新鲜度窗口：
// 缺席取默认 120s，越界值启动失败而不是被静默夹取成默认值。
func TestValidatePlatformOpsConfigBoundsConfigAckMaxAge(t *testing.T) {
	cfg := validPlatformOpsConfig()
	if seconds := cfg.configAckMaxAgeSeconds(); seconds != defaultConfigAckMaxAgeSeconds {
		t.Fatalf("absent max age must default to %d, got %d", defaultConfigAckMaxAgeSeconds, seconds)
	}
	cfg.ConfigAck.MaxAgeSeconds = 10
	if err := validatePlatformOpsConfig(cfg); err == nil {
		t.Fatal("out-of-range config_ack.max_age_seconds must fail closed")
	}
	cfg.ConfigAck.MaxAgeSeconds = 300
	if err := validatePlatformOpsConfig(cfg); err != nil {
		t.Fatalf("in-range config_ack.max_age_seconds must pass: %v", err)
	}
	if seconds := cfg.configAckMaxAgeSeconds(); seconds != 300 {
		t.Fatalf("declared max age must win, got %d", seconds)
	}
}

// TestValidatePlatformOpsConfigRequiresProdReleaseDigest 锁定生产的发布包
// digest 必填：收敛判据以它为锚，缺它则无法证明当前发布包已下发。
func TestValidatePlatformOpsConfigRequiresProdReleaseDigest(t *testing.T) {
	cfg := validPlatformOpsConfig()
	cfg.Environment = "prod"
	cfg.ReleaseManifestDigest = ""
	if err := validatePlatformOpsConfig(cfg); err == nil {
		t.Fatal("prod without RELEASE_MANIFEST_DIGEST must fail closed")
	}
	cfg.ReleaseManifestDigest = "not-a-digest"
	if err := validatePlatformOpsConfig(cfg); err == nil {
		t.Fatal("prod with a non-canonical digest must fail closed")
	}
	cfg.ReleaseManifestDigest = "sha256:" + strings.Repeat("a", 64)
	cfg.HumanAuthority.Issuer = "quwoquan-platform-ops"
	cfg.HumanAuthority.ProviderVersion = "v1"
	cfg.HumanAuthority.ProviderCommit = "sha256:" + strings.Repeat("b", 64)
	cfg.HumanAuthority.SigningKeyID = "prod-key"
	cfg.HumanAuthority.SigningPrivateKeyFile = "/run/secrets/human-authority-key"
	cfg.HumanAuthority.GitHubWebhookSecret = "secret-reference-placeholder"
	cfg.HumanAuthority.RoleMappings = `{"ops-release":["release_owner"]}`
	if err := validatePlatformOpsConfig(cfg); err != nil {
		t.Fatalf("canonical prod digest must pass: %v", err)
	}
}

// TestRequiredConfigAckInstancesNormalizes 锁定收敛判定与注入顺序无关：
// 去空、去重、排序。
func TestRequiredConfigAckInstancesNormalizes(t *testing.T) {
	service := &platformService{
		configAckInstances: []string{"b-1", " ", "a-1", "b-1"},
	}
	instances := service.requiredConfigAckInstances()
	if len(instances) != 2 || instances[0] != "a-1" || instances[1] != "b-1" {
		t.Fatalf("expected deduplicated sorted instances, got %v", instances)
	}
}

func validPlatformOpsConfig() *config {
	cfg := &config{}
	cfg.Environment = "gamma"
	cfg.Service.HTTP.Addr = ":18088"
	cfg.Postgres.DSN = "postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable"
	cfg.Redis.General.Mode = servicekit.RedisModeStandalone
	cfg.Redis.General.Addr = "redis:6379"
	cfg.RepoRoot = "/app"
	return cfg
}
