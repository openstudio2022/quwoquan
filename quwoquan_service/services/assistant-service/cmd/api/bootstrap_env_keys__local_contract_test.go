package bootstrap

import (
	"testing"
)

// TestDeclaredEnvKeysCoverHandwrittenOverrides 锁定声明式配置派生的 env 覆盖
// 键集覆盖迁移前手写 ApplyEnvOverrides 的每一个语义位；无服务前缀的旧键退役，
// 不与新键并存双读。
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
		// 监听地址与出向依赖：迁移前后逐字一致，注入点无需改动。
		"ASSISTANT_SERVICE_ADDR",
		"ASSISTANT_CHAT_BASE_URL",
		"ASSISTANT_CIRCLE_BASE_URL",
		"ASSISTANT_USER_SERVICE_BASE_URL",
		"ASSISTANT_NOTIFICATION_BASE_URL",
		"ASSISTANT_SEARCH_SERVICE_BASE_URL",
		"ASSISTANT_ENTITY_SERVICE_BASE_URL",
		"ASSISTANT_CONTENT_SERVICE_BASE_URL",
		"ASSISTANT_INTEGRATION_BASE_URL",
		"ASSISTANT_SKILL_PACKAGE_ROOT",
		"ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON",
		// 数据面：由无前缀键改为服务前缀键，compose 与 prod plane 注入同步更新。
		"ASSISTANT_MONGO_URI",
		"ASSISTANT_MONGO_DATABASE",
		"ASSISTANT_POSTGRES_DSN",
		"ASSISTANT_REDIS_GENERAL_MODE",
		"ASSISTANT_REDIS_GENERAL_ADDR",
		"ASSISTANT_REDIS_GENERAL_ADDRS",
		"ASSISTANT_REDIS_GENERAL_PASSWORD",
		"ASSISTANT_REDIS_GENERAL_TLS",
		"ASSISTANT_REDIS_GENERAL_DB",
		"ASSISTANT_REDIS_REC_MODE",
		"ASSISTANT_REDIS_REC_ADDR",
		"ASSISTANT_REDIS_REC_ADDRS",
		"ASSISTANT_REDIS_REC_PASSWORD",
		"ASSISTANT_REDIS_REC_TLS",
		"ASSISTANT_REDIS_REC_DB",
	} {
		if !declared[required] {
			t.Fatalf("declared env keys missing %s", required)
		}
	}
	for _, retired := range retiredEnvKeys() {
		if declared[retired] {
			t.Fatalf("retired env key %s is still declared", retired)
		}
	}
}

// TestValidateAssistantConfigRequiresRealRedisScenes 锁定 fail-closed：
// general/rec scene 缺少真实组网声明时不得回落 memory——会话与推荐上下文
// 落进单实例内存等于静默丢数据。
func TestValidateAssistantConfigRequiresRealRedisScenes(t *testing.T) {
	cfg := completeAssistantEgressConfig()
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = ""
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "redis:6379"
	if err := validateAssistantConfig(cfg); err == nil {
		t.Fatal("expected standalone general scene without addr to be rejected")
	}

	cfg.Redis.General.Addr = "redis:6379"
	if err := validateAssistantConfig(cfg); err != nil {
		t.Fatalf("declared scenes must pass: %v", err)
	}

	cfg.Redis.Rec.Mode = "memory"
	if err := validateAssistantConfig(cfg); err == nil {
		t.Fatal("expected memory mode to be rejected outside the declared modes")
	}
}

// TestResolveRedisScenesReusesGeneralForRealtime 锁定 scene 映射：realtime
// 复用 general 的物理实例，rec 独立，与 codegen 的前缀路由同源。
func TestResolveRedisScenesReusesGeneralForRealtime(t *testing.T) {
	cfg := completeAssistantEgressConfig()
	cfg.Redis.General.Addr = "redis-general:6379"
	cfg.Redis.Rec.Addr = "redis-rec:6379"

	scenes := resolveRedisScenes(cfg)
	if len(scenes) != 3 {
		t.Fatalf("expected general/rec/realtime scenes, got %v", scenes)
	}
	if scenes["realtime"].Addr != scenes["general"].Addr {
		t.Fatalf(
			"realtime must reuse general: realtime=%s general=%s",
			scenes["realtime"].Addr, scenes["general"].Addr,
		)
	}
	if scenes["rec"].Addr == scenes["general"].Addr {
		t.Fatal("rec scene must stay independent from general")
	}
}

func completeAssistantEgressConfig() *config {
	cfg := &config{}
	cfg.NotificationService.BaseURL = "http://notification-service:18087"
	cfg.UserService.BaseURL = "http://user-service:18081"
	cfg.ChatService.BaseURL = "http://chat-service:18081"
	cfg.SearchService.BaseURL = "http://search-service:18085"
	cfg.EntityService.BaseURL = "http://entity-service:18084"
	cfg.ContentService.BaseURL = "http://content-service:18083"
	cfg.IntegrationService.BaseURL = "http://integration-service:18086"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "redis:6379"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "redis:6379"
	return cfg
}
