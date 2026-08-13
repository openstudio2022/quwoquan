// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
// 错误契约语义双向锁：connector gateway 依赖失败的 domain sentinel 由真实依赖缺失
// 触发；canonical code 的 App 语义（用户提示 / 恢复指令）与 errors.yaml 同源锁定。
// upstream_timeout 当前在服务内没有第一方发射点，只锁 canonical 语义，防止声明与
// generated 映射漂移。
package assistant_run_test

import (
	"errors"
	"testing"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
)

func TestConnectorGatewayOutageEmitsCanonicalUnavailableSemantics(t *testing.T) {
	t.Parallel()
	// 真实依赖失败：声明了 consent scope 的能力在 consent reader 缺失时必须
	// fail-closed 到 gateway-unavailable，而不是放行。
	_, err := toolaccess.NewPolicy(nil, nil, nil).Authorize(
		t.Context(),
		toolaccess.Request{
			AccountID: "account-connector-error",
			SkillID:   "travel_companion",
			Requirement: toolaccess.Requirement{
				CapabilityKey:        "context.gathering",
				ConnectorRequirement: toolaccess.ConnectorNone,
				ConsentScopes:        []string{"assistant.memory.preferences.read"},
				AllowedSurfaceKinds:  []string{toolaccess.SurfacePersonal},
				RecheckAtExecution:   true,
			},
		},
	)
	if !errors.Is(err, toolaccess.ErrGatewayUnavailable) {
		t.Fatalf("gateway outage sentinel = %v", err)
	}
	// 装配层把该 sentinel 映射为 canonical code（cmd/api composition 的
	// configureAgentToolAccess default 分支）；这里锁定映射产物的双向语义。
	appErr := runerrors.AppErrorFromConnectorGatewayUnavailable(err.Error())
	if appErr.Code.String() != "ASSISTANT.SYSTEM.connector_gateway_unavailable" ||
		appErr.Recovery.Action != "retry" {
		t.Fatalf(
			"connector gateway canonical semantics drifted: code=%s recovery=%+v",
			appErr.Code.String(),
			appErr.Recovery,
		)
	}
	if !errors.Is(runerrors.ErrConnectorGatewayUnavailable, runerrors.ErrConnectorGatewayUnavailable) ||
		runerrors.ErrConnectorGatewayUnavailable.Error() !=
			"ASSISTANT.SYSTEM.connector_gateway_unavailable" {
		t.Fatalf(
			"generated sentinel drifted: %v",
			runerrors.ErrConnectorGatewayUnavailable,
		)
	}
}

func TestUpstreamTimeoutKeepsCanonicalRetrySemantics(t *testing.T) {
	t.Parallel()
	appErr := runerrors.AppErrorFromUpstreamTimeout("model provider deadline exceeded")
	if appErr.Code.String() != "ASSISTANT.MIDDLEWARE.upstream_timeout" ||
		appErr.Recovery.Action != "retry" {
		t.Fatalf(
			"upstream timeout canonical semantics drifted: code=%s recovery=%+v",
			appErr.Code.String(),
			appErr.Recovery,
		)
	}
	if runerrors.ErrUpstreamTimeout.Error() != "ASSISTANT.MIDDLEWARE.upstream_timeout" {
		t.Fatalf("generated sentinel drifted: %v", runerrors.ErrUpstreamTimeout)
	}
}
