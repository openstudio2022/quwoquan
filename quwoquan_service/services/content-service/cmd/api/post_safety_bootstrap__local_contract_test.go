package bootstrap

import (
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestPostSafetyBootstrapRejectsUnverifiedRuntime(t *testing.T) {
	for _, env := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(env, func(t *testing.T) {
			cfg := &config{}
			cfg.Environment = env
			for _, tc := range []struct{ key, receipt, root, current, want string }{
				{"", "", "", "", "hmac_secret_ref"},
				{"managed-key-ref", "", "", "", "recovery_evidence_ref"},
				{"managed-key-ref", "fact.json", "", "", "material_root"},
				{"managed-key-ref", "fact.json", "/managed/post-safety", "", "current_binding_ref"},
			} {
				cfg.PostSafety.HMACSecretRef = tc.key
				cfg.PostSafety.RecoveryEvidenceRef = tc.receipt
				cfg.PostSafety.MaterialRoot = tc.root
				cfg.PostSafety.CurrentBindingRef = tc.current
				// 校验正式ValidateConfig的安全子门；不声称此单测启动了HTTP或连接数据库。
				err := validatePostSafetyBootstrap(cfg)
				if err == nil || !strings.Contains(err.Error(), "CONTENT.RELEASE.query_barrier_not_ready") || !strings.Contains(err.Error(), tc.want) {
					t.Fatalf("unexpected startup result: %v", err)
				}
				if strings.Contains(err.Error(), "managed-key-ref") || strings.Contains(err.Error(), "fact.json") || strings.Contains(err.Error(), "/managed/") {
					t.Fatal("configuration value leaked")
				}
			}
		})
	}
}
