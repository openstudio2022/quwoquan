// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
//
// api-edge 的入站顺序是 services/api-edge/AGENTS.md 的明文契约：
//
//	credential verification -> generated operation authorization
//	-> shared admission -> owner proxy
//
// 迁移到声明式骨架之前，这个顺序只由 cmd/api/main.go 里一段注释表达，没有
// 任何测试锁住它。本文件把它变成取证：每一层记录自己的执行，再断言完整序列。
package bootstrap

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
)

// recordingMiddleware 在请求穿过自己时追加一条记录，用于取证层序。
func recordingMiddleware(order *[]string, label string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			*order = append(*order, label)
			next.ServeHTTP(writer, request)
		})
	}
}

// TestInboundOrderMatchesTheDeclaredEdgeContract 穿过生产装配实际使用的两个
// 复合函数（edgeOperationGuard 与 edgeBusinessSurface），加上骨架负责的两层
// 位置，断言 AGENTS.md 的契约顺序逐层成立。
//
// 层与声明位的对应：
//   - credential relay 是 BootstrapSpec.WrapOutsideAuth，取生产实际值；
//   - credential verification 是骨架 auth 栈，它固定在 WrapOutsideAuth 内侧、
//     WrapHandler/CORS/观测栈外侧，该位置由 servicekit 自己的
//     TestWrapOutsideAuthObservesRequestBeforeAuthentication 锁定，本测试以
//     同位置的记录层代表它；
//   - minimum build 与 operation authorization 穿过 edgeOperationGuard；
//   - shared admission 与 rollout decision 穿过 edgeBusinessSurface。
func TestInboundOrderMatchesTheDeclaredEdgeContract(t *testing.T) {
	var order []string

	ownerProxy := http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		order = append(order, "owner_proxy")
		writer.WriteHeader(http.StatusNoContent)
	})
	business := edgeBusinessSurface(
		recordingMiddleware(&order, "shared_admission"),
		recordingMiddleware(&order, "rollout_decision"),
		ownerProxy,
	)
	guard := edgeOperationGuard(
		recordingMiddleware(&order, "minimum_build"),
		recordingMiddleware(&order, "generated_operation_authorization"),
	)
	authenticated := recordingMiddleware(
		&order, "credential_verification",
	)(guard(business))

	spec := newBootstrapSpec()
	if spec.WrapOutsideAuth == nil {
		t.Fatal("credential relay must be declared outside the authentication middleware")
	}
	handler := spec.WrapOutsideAuth(
		recordingMiddleware(&order, "credential_relay")(authenticated),
	)

	request := httptest.NewRequest(http.MethodGet, "/content/posts/abc", nil)
	request.Header.Set("Authorization", "Bearer edge-order-probe")
	handler.ServeHTTP(httptest.NewRecorder(), request)

	expected := []string{
		"credential_relay",
		"credential_verification",
		"minimum_build",
		"generated_operation_authorization",
		"shared_admission",
		"rollout_decision",
		"owner_proxy",
	}
	if strings.Join(order, ">") != strings.Join(expected, ">") {
		t.Fatalf(
			"入站顺序偏离 AGENTS.md 契约：\n got %v\nwant %v",
			order, expected,
		)
	}
}

// TestCredentialRelayObservesTheRawCredentialBeforeAuthentication 取证凭据中继
// 必须先于认证看到原始报文：认证会删掉 Authorization 与 X-Device-Ticket，
// owner proxy 只能靠中继在认证之前捕获的那一份来恢复它们。挂错到 WrapHandler
// （认证内侧）就只能看到已被清空的头。
func TestCredentialRelayObservesTheRawCredentialBeforeAuthentication(t *testing.T) {
	spec := newBootstrapSpec()
	if spec.WrapOutsideAuth == nil {
		t.Fatal("credential relay must be declared")
	}

	var relayedTicket, authenticatedTicket string
	authentication := rtauth.Middleware(rtauth.MiddlewareConfig{})
	// 一次请求取两个观察点：中继之后、认证之前，以及认证之内。
	handler := spec.WrapOutsideAuth(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			relayedTicket = request.Header.Get(rtauth.DeviceTicketHeader)
			authentication(http.HandlerFunc(
				func(_ http.ResponseWriter, authenticated *http.Request) {
					authenticatedTicket = authenticated.Header.Get(
						rtauth.DeviceTicketHeader,
					)
				},
			)).ServeHTTP(writer, request)
		},
	))

	request := httptest.NewRequest(http.MethodGet, "/content/posts/abc", nil)
	request.Header.Set(rtauth.DeviceTicketHeader, "device-ticket-probe")
	handler.ServeHTTP(httptest.NewRecorder(), request)

	if relayedTicket != "device-ticket-probe" {
		t.Fatalf(
			"credential relay must still see the raw credential, got %q",
			relayedTicket,
		)
	}
	// 认证内侧已看不到原始凭据，因此中继只有挂在认证之外才有意义。
	if authenticatedTicket != "" {
		t.Fatalf(
			"authentication must strip the raw credential, got %q",
			authenticatedTicket,
		)
	}
}

// TestEdgeDeclaresNoBrowserCORSSurface 锁定迁移等价性里最容易悄悄漂移的一条：
// api-edge 迁移前不挂载任何跨域中间件，OPTIONS 由 ContractGraph 裁决为
// route_not_found。一旦声明 CORS，rthttp.WithCORS 会对全部路径的 OPTIONS
// 无条件短路返回 204——那是一个不过观测、不过 operation guard、不过共享准入
// 的未认证面，出现在全站唯一对外入口上。
func TestEdgeDeclaresNoBrowserCORSSurface(t *testing.T) {
	spec := newBootstrapSpec()
	if spec.CORS != nil {
		t.Fatal("api-edge 不接受浏览器跨域直连，不得声明 CORS 策略")
	}
}

// TestMinimumBuildGateStaysInsideTheOperationGuard 锁定 2.3 的位置裁决：最低
// 支持版本闸门必须复合进 OperationGuard，不能挂到 WrapHandler。骨架只用
// guard 包 assembly.Mux，而 WrapHandler 覆盖 /healthz、/readyz、/metrics、
// /graphql 与 /realtime/ws——迁移前这五个面都不过最低版本闸门。
func TestMinimumBuildGateStaysInsideTheOperationGuard(t *testing.T) {
	spec := newBootstrapSpec()
	if spec.WrapHandler != nil {
		t.Fatal(
			"认证内侧不得有服务级中间件：最低版本闸门属于 OperationGuard，" +
				"挂到 WrapHandler 会把它扩到探针与 unguarded 面",
		)
	}
	if spec.OperationGuard == nil {
		t.Fatal("api-edge 必须声明按环境分档的 operation guard")
	}
}
