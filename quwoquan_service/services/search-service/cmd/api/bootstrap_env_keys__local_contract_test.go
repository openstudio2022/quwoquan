package bootstrap

import (
	"strings"
	"testing"
)

// TestDeclaredEnvKeysCoverHandwrittenOverrides 锁定声明式配置派生的 env 覆盖键
// 集覆盖迁移前手写 applyESEnvOverrides / applyMongoEnvOverrides /
// applyRedisSceneEnv / getenvInt 的全部键。SEARCH_ES_* 与 CONTENT_SERVICE_BASE_URL
// 是部署面与其他服务共享的注入键，必须逐字保留，不允许被服务前缀改名。
func TestDeclaredEnvKeysCoverHandwrittenOverrides(t *testing.T) {
	keys, err := DeclaredEnvKeys()
	if err != nil {
		t.Fatalf("declared env keys: %v", err)
	}
	declared := map[string]bool{}
	for _, key := range keys {
		declared[key] = true
	}
	for _, required := range []string{
		"SEARCH_SERVICE_ADDR",
		"SEARCH_ES_ENABLED",
		"SEARCH_ES_ENDPOINTS",
		"SEARCH_ES_USERNAME",
		"SEARCH_ES_PASSWORD",
		"SEARCH_ES_API_KEY",
		"SEARCH_MONGO_URI",
		"SEARCH_MONGO_DATABASE",
		"SEARCH_REDIS_GENERAL_MODE",
		"SEARCH_REDIS_GENERAL_ADDR",
		"SEARCH_REDIS_GENERAL_ADDRS",
		"SEARCH_REDIS_GENERAL_PASSWORD",
		"SEARCH_REDIS_GENERAL_TLS",
		"SEARCH_REDIS_REC_MODE",
		"SEARCH_REDIS_REC_ADDR",
		"SEARCH_REDIS_REC_ADDRS",
		"SEARCH_REDIS_REC_PASSWORD",
		"SEARCH_REDIS_REC_TLS",
		"SEARCH_MAX_INFLIGHT",
		"SEARCH_RELATED_TERMS_CACHE_TTL_MS",
		"SEARCH_RELATED_TERMS_CACHE_MAX",
		"CONTENT_SERVICE_BASE_URL",
	} {
		if !declared[required] {
			t.Fatalf("declared env keys missing %s", required)
		}
	}
	// 索引形状与分片策略决定物理索引的可兼容性，必须随配置包被 CONFIG_VERSION
	// 钉住；任何 env 旁路都会让同一 CONFIG_VERSION 产出不同索引 mapping。
	for _, forbidden := range []string{
		"SEARCH_ES_INDEX",
		"SEARCH_ES_SHARDS",
		"SEARCH_ES_REPLICAS",
		"SEARCH_ES_SYNONYMS",
		"SEARCH_ES_EMBEDDING_DIMS",
	} {
		if declared[forbidden] {
			t.Fatalf("index shape must not be env-overridable: %s", forbidden)
		}
	}
	// 共享的 ES 部署契约键不得被服务前缀改名，否则 content-service /
	// entity-service 的同名注入会对本服务失效。
	for _, key := range keys {
		if strings.HasPrefix(key, "SEARCH_SEARCH_ES_") {
			t.Fatalf("shared ES contract key was prefixed: %s", key)
		}
	}
}

// TestValidateSearchConfigRejectsNonPositiveServingBounds 锁定 fail-closed：
// 迁移前 getenvInt 会把 0/负数静默换成内建默认值，从而让「注入了非法上界」
// 与「没注入」不可区分。
func TestValidateSearchConfigRejectsNonPositiveServingBounds(t *testing.T) {
	newValidConfig := func() *config {
		cfg := &config{}
		cfg.ES.Index = "quwoquan_objects"
		cfg.Serving.MaxInflight = 256
		cfg.Serving.RelatedTermsCacheTTLMs = 2000
		cfg.Serving.RelatedTermsCacheMax = 1024
		cfg.UserAccountSecurityAuthority.TimeoutMs = 300
		return cfg
	}
	if err := validateSearchConfig(newValidConfig()); err != nil {
		t.Fatalf("rendered snapshot defaults must pass: %v", err)
	}
	for name, mutate := range map[string]func(*config){
		"es.index":                                   func(cfg *config) { cfg.ES.Index = " " },
		"serving.max_inflight":                       func(cfg *config) { cfg.Serving.MaxInflight = 0 },
		"serving.related_terms_cache_ttl_ms":         func(cfg *config) { cfg.Serving.RelatedTermsCacheTTLMs = -1 },
		"serving.related_terms_cache_max":            func(cfg *config) { cfg.Serving.RelatedTermsCacheMax = 0 },
		"user_account_security_authority.timeout_ms": func(cfg *config) { cfg.UserAccountSecurityAuthority.TimeoutMs = 0 },
	} {
		cfg := newValidConfig()
		mutate(cfg)
		if err := validateSearchConfig(cfg); err == nil {
			t.Fatalf("expected %s rejection", name)
		}
	}
}

// TestSnapshotGuardRejectsRetiredAuthoritySection 锁定旧配置段的原文拒收：
// 一个仍带 accountSecurityAuthority 的快照被挂进来时，新代码只会读到零值，
// 必须启动失败而不是带空 authority 地址继续。
func TestSnapshotGuardRejectsRetiredAuthoritySection(t *testing.T) {
	retired := []byte(
		"accountSecurityAuthority:\n  baseUrl: http://user-service:18081\n  timeoutMs: 300\n",
	)
	if err := rejectRetiredSearchSnapshotSections(retired); err == nil {
		t.Fatal("expected retired accountSecurityAuthority section rejection")
	}
	current := []byte(
		"user_account_security_authority:\n  base_url: http://user-service:18081\n" +
			"  timeout_ms: 300\nserving:\n  max_inflight: 256\n",
	)
	if err := rejectRetiredSearchSnapshotSections(current); err != nil {
		t.Fatalf("current snapshot shape must pass: %v", err)
	}
}
