// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-005
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#open-008
//
// 限流策略装配合约：rate_limit 配置段解析后，PolicySet 必须携带匿名恢复
// 上报的专属 operation override（OPEN-008 上收的声明面），且与既有
// content feed override 共存互不覆盖。
package bootstrap

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
)

func configFileForEnvironment(environment string) (string, error) {
	raw, err := os.ReadFile(filepath.Join(
		"..", "..", "environments", environment, "config.yaml",
	))
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func containsKey(raw, key string) bool {
	return strings.Contains(raw, key+":")
}

const rateLimitConfigFixture = `
rate_limit:
  command:
    limit: 60
    window_seconds: 60
    state_failure: fail_closed
  query:
    limit: 240
    window_seconds: 60
    state_failure: fail_closed
  session:
    limit: 120
    window_seconds: 60
    state_failure: fail_closed
  operation:
    content_post_get_feed:
      limit: 400
      window_seconds: 1
      state_failure: fail_closed
    ops_recovery_failure_report:
      limit: 30
      window_seconds: 60
      state_failure: fail_closed
`

func TestPolicySetCarriesRecoveryFailureOperationOverride(t *testing.T) {
	var config runtimeConfig
	if err := yaml.Unmarshal([]byte(rateLimitConfigFixture), &config); err != nil {
		t.Fatalf("parse rate limit fixture: %v", err)
	}
	policies := config.policySet()
	if err := policies.Validate(); err != nil {
		t.Fatalf("policy set must validate: %v", err)
	}

	recovery, exists := policies.ByOperationID["ops.recovery_failure.ReportRecoveryFailure"]
	if !exists {
		t.Fatal("anonymous recovery admission override is missing from the policy set")
	}
	if recovery.Limit != 30 ||
		recovery.Window != time.Minute ||
		recovery.StateFailure != domain.FailurePolicyFailClosed {
		t.Fatalf("recovery override drifted from configuration: %+v", recovery)
	}

	feed, exists := policies.ByOperationID["content.post.GetFeed"]
	if !exists {
		t.Fatal("existing feed override must coexist with the recovery override")
	}
	if feed.Limit != 400 || feed.Window != time.Second {
		t.Fatalf("feed override drifted: %+v", feed)
	}

	if command := policies.ByOperationKind["command"]; command.Limit != 60 {
		t.Fatalf("operation overrides must not mutate kind defaults: %+v", command)
	}
}

// 四环境 config.yaml 必须都声明恢复上报 override 的三个键；缺任一环境
// 意味着该环境的匿名准入回退到 command 缺省，等于放宽日志端口容量预算。
func TestAllEnvironmentsDeclareTheRecoveryAdmissionKeys(t *testing.T) {
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		raw, err := configFileForEnvironment(environment)
		if err != nil {
			t.Fatalf("read %s config: %v", environment, err)
		}
		for _, key := range []string{
			"sys.api-edge.rate_limit.operation.ops_recovery_failure_report.limit",
			"sys.api-edge.rate_limit.operation.ops_recovery_failure_report.window_seconds",
			"sys.api-edge.rate_limit.operation.ops_recovery_failure_report.state_failure",
		} {
			if !containsKey(raw, key) {
				t.Fatalf("%s config misses %s", environment, key)
			}
		}
	}
}
