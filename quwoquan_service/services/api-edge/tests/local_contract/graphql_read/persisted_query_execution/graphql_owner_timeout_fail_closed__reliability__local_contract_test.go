// GraphQL 读边缘的下游 owner 超时/失败可靠性契约：fail-closed、错误码契约闭集、零伪成功。
//
// 故障语义唯一真相源是 contracts/graphql_read/persisted_query_execution/errors.yaml
// 的 GATEWAY.MIDDLEWARE.graphql_owner_unavailable（503）；本测试不建立第二错误清单。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"testing"
)

func TestGraphqlOwnerTimeoutFailsClosedWithContractError(t *testing.T) {
	for name, ownerError := range map[string]error{
		"下游超时": context.DeadlineExceeded,
		"下游拒绝": errors.New("owner connection refused"),
		"下游取消": context.Canceled,
	} {
		t.Run(name, func(t *testing.T) {
			authorizer := &contractAuthorizer{}
			executor := &contractExecutor{err: ownerError}
			handler := newContractHandler(t, authorizer, executor)

			response := serveGraphQL(t, handler, map[string]any{
				"extensions": map[string]any{
					"persistedQuery": map[string]any{
						"version":    1,
						"sha256Hash": validRegistryEntry().SHA256Hash,
					},
				},
			})

			// fail-closed：503 + 契约闭集错误码，不得返回部分数据伪成功。
			assertRuntimeError(
				t,
				response,
				http.StatusServiceUnavailable,
				"GATEWAY.MIDDLEWARE.graphql_owner_unavailable",
			)
			if executor.calls != 1 {
				t.Fatalf("executor calls=%d want=1（边缘不得自行重试放大下游故障）", executor.calls)
			}
		})
	}
}
