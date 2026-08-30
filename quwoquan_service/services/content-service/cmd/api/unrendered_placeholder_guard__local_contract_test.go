// spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/go-integration/spec.md#open-002
package bootstrap

import (
	"strings"
	"testing"
)

// placeholderGuardFixture 只让校验链走到未展开占位符那一段：三个 Redis scene
// 组网合法（占位符检查在它之后），feed 预算留零值（占位符检查在它之前）。
// 因此「占位符在场」与「占位符缺席」两条路径的错误可区分，负例不会被别的
// 校验抢先判否而假装通过。
func placeholderGuardFixture() *config {
	cfg := &config{}
	cfg.Environment = "prod"
	for _, scene := range []*redisSceneCfg{
		&cfg.Redis.Rec, &cfg.Redis.General, &cfg.Redis.Realtime,
	} {
		scene.Mode = "standalone"
		scene.Addr = "redis.internal:6379"
	}
	return cfg
}

// 渲染型配置值在渲染缺失时会以未展开的 `${KEY}` 字面量进入快照。字面量对
// required 校验是「在场」，对上游客户端的「url 为空则不装配」判据也是
// 「在场」——服务于是带着假地址启动，把一个配置缺陷表达成运行期调用失败。
// 本测试锁定这些键在启动即 fail-closed。
func TestUnrenderedPlaceholdersFailStartup(t *testing.T) {
	guarded := map[string]func(cfg *config){
		"mongo.uri": func(cfg *config) {
			cfg.Mongo.URI = "${CONTENT_MONGO_URI}"
		},
		"postgres.report_dsn": func(cfg *config) {
			cfg.Postgres.ReportDSN = "${CONTENT_POSTGRES_REPORT_DSN}"
		},
		"rec_model_service.url": func(cfg *config) {
			cfg.RecModelService.URL = "${REC_MODEL_SERVICE_URL}"
		},
		"tag_service.url": func(cfg *config) {
			cfg.TagService.URL = "${TAG_SERVICE_URL}"
		},
		"user_account_security_authority.base_url": func(cfg *config) {
			cfg.UserAccountSecurityAuthority.BaseURL = "${CONTENT_AUTHORITY_BASE_URL}"
		},
	}
	for name, mutate := range guarded {
		t.Run(name, func(t *testing.T) {
			cfg := placeholderGuardFixture()
			mutate(cfg)
			err := validateContentConfig(cfg)
			if err == nil {
				t.Fatalf("未展开占位符必须让 %s 在启动即失败", name)
			}
			if !strings.Contains(err.Error(), "unrendered placeholder") ||
				!strings.Contains(err.Error(), name) {
				t.Fatalf("%s 的失败必须指认该键的渲染缺失，得到 %v", name, err)
			}
		})
	}
}

// TestPlaceholderGuardFixtureClearsTheGuard 证明上面的负例确实由占位符触发：
// 同一 fixture 不注入占位符时，控制流越过占位符段（错误来自后续的 feed 预算
// 校验，而不是占位符判否）。
func TestPlaceholderGuardFixtureClearsTheGuard(t *testing.T) {
	err := validateContentConfig(placeholderGuardFixture())
	if err == nil {
		t.Fatal("零值 feed 预算必须被后续校验判否，fixture 假设已失效")
	}
	if strings.Contains(err.Error(), "unrendered placeholder") {
		t.Fatalf("无占位符的 fixture 不得被占位符段判否，得到 %v", err)
	}
}
