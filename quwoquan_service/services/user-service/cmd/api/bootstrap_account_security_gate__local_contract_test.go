// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t5
package bootstrap

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/servicekit"
	httpadapter "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

const closeAccountPath = "/owner/account/close"

// closedAccountSecurityReader 是本测试自己的权威状态读取面，不进生产装配：
// 生产装配读的是 useraccountpersistence.EnforcementStore。
type closedAccountSecurityReader struct{}

func (closedAccountSecurityReader) ReadAccountSecurity(
	context.Context, string,
) (accountports.AccountSecuritySnapshot, error) {
	return accountports.AccountSecuritySnapshot{
		AccountState: "closed",
		AuthEpoch:    3,
	}, nil
}

// newAccountSecurityGateForTest 取的就是生产装配交给骨架的那一个 gate 函数
// （httpadapter.UserHandler.WrapAccountSecurity），判据逻辑不复制、不改写。
func newAccountSecurityGateForTest() func(http.Handler) http.Handler {
	handler := (&httpadapter.UserHandler{}).WithAccountSecurityReader(
		closedAccountSecurityReader{},
	)
	return handler.WrapAccountSecurity
}

func closedAccountCloseRequest() *http.Request {
	request := httptest.NewRequest(http.MethodPost, closeAccountPath, nil)
	request.Header.Set("Idempotency-Key", "close-replay-local-contract")
	principal := rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType: rtauth.TokenTypeAccess,
			AuthEpoch: 3,
		},
		Actor: operation.ActorContext{AccountID: "closed_account_replay"},
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

// TestBootstrapSpecDeclaresSelfHostedAuthorityAndPreAdmissionPath 锁定交出点的
// 声明侧：只要 SelfHostedAccountSecurityAuthority 在场，骨架就
// (a) 要求 Assemble 交出进程内裁决 gate，缺则启动失败，
// (b) 把该 gate 挂在 operation guard **内侧**。
// 两条都由 servicekit 的 TestSelfHostedAuthorityRequiresInProcessGate 与
// TestInProcessGateRunsInsideOperationGuard 取证，此处断言 user-service 确实
// 落在那条声明分支上，而不是退回「认证层持有 authority」的旧形态。
func TestBootstrapSpecDeclaresSelfHostedAuthorityAndPreAdmissionPath(t *testing.T) {
	spec := userBootstrapSpec()
	if !spec.SelfHostedAccountSecurityAuthority {
		t.Fatal("user-service hosts the account security authority in process")
	}
	if spec.SkipAccountSecurityAuthority {
		t.Fatal("user-service accepts end-user account principals; it must not skip adjudication")
	}
	if spec.AuthorityScopes != nil {
		t.Fatalf("a self-hosted authority must not declare authority scopes, got %v", spec.AuthorityScopes)
	}
	if spec.OperationGuard == nil {
		t.Fatal("the in-process gate reads operation context; the guard must be declared")
	}
	if len(spec.PreAdmissionPaths) != 1 ||
		spec.PreAdmissionPaths[0] != accountSecurityHealthPath {
		t.Fatalf("pre-admission paths drifted: %v", spec.PreAdmissionPaths)
	}
}

// TestCloseAccountReplayPassesTheGateInsideTheOperationGuard 直接打行为：按骨架
// 的挂载顺序 guard(gate(routes)) 组装，已确认 closed 的账号重放 CloseAccount
// 必须穿过账号安全 gate 到达业务 Handler（metadata 契约要求幂等成功），而同一
// 账号访问其他 operation 仍被 gate 以 account_deleted 拒绝。
func TestCloseAccountReplayPassesTheGateInsideTheOperationGuard(t *testing.T) {
	guard, err := newUserOperationGuard(servicekit.Identity{
		ServiceName: serviceName,
		AppEnv:      "alpha",
	})
	if err != nil {
		t.Fatalf("operation guard: %v", err)
	}

	reached := false
	routes := http.NewServeMux()
	routes.HandleFunc(
		http.MethodPost+" "+closeAccountPath,
		func(w http.ResponseWriter, r *http.Request) {
			reached = true
			if invocation, ok := operation.FromContext(r.Context()); !ok ||
				invocation.OperationID != "user.user_account.CloseAccount" {
				t.Errorf("operation context missing at the domain handler: %#v", invocation)
			}
			w.WriteHeader(http.StatusOK)
		},
	)
	gate := newAccountSecurityGateForTest()

	// 骨架的实际挂载顺序：guard 先写入 operation 上下文，gate 才能读到它。
	response := httptest.NewRecorder()
	guard(gate(routes)).ServeHTTP(response, closedAccountCloseRequest())
	if response.Code != http.StatusOK || !reached {
		t.Fatalf(
			"closed account must replay CloseAccount idempotently: status=%d reached=%t body=%s",
			response.Code, reached, response.Body.String(),
		)
	}
}

// TestGateOutsideTheOperationGuardBreaksCloseAccountReplay 是上面那条的反例
// 对照：把 gate 挪到 guard 外侧（被否决的「注入认证层」形态所在的位置），
// operation 上下文尚未写入，gate 读不到 CloseAccount 这个 operation ID，
// closed 终态重放就会被判成 account_deleted。这条测试是「挂载位置由骨架决定
// 而非服务侧手工组装」的必要性取证：位置错了在运行期只表现为某条幂等重放
// 语义悄悄失效，没有任何启动信号。
func TestGateOutsideTheOperationGuardBreaksCloseAccountReplay(t *testing.T) {
	guard, err := newUserOperationGuard(servicekit.Identity{
		ServiceName: serviceName,
		AppEnv:      "alpha",
	})
	if err != nil {
		t.Fatalf("operation guard: %v", err)
	}

	reached := false
	routes := http.NewServeMux()
	routes.HandleFunc(
		http.MethodPost+" "+closeAccountPath,
		func(w http.ResponseWriter, _ *http.Request) {
			reached = true
			w.WriteHeader(http.StatusOK)
		},
	)
	gate := newAccountSecurityGateForTest()

	response := httptest.NewRecorder()
	gate(guard(routes)).ServeHTTP(response, closedAccountCloseRequest())
	if response.Code != http.StatusGone || reached {
		t.Fatalf(
			"a gate outside the guard cannot honour the replay exemption: status=%d reached=%t body=%s",
			response.Code, reached, response.Body.String(),
		)
	}
}
