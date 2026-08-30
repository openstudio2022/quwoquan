package bootstrap

import (
	"errors"
	"net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rtgov "quwoquan_service/runtime/governance"
	"quwoquan_service/runtime/servicekit"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
)

// contentAPIRuntime 把「只有装配期才知道的领域参数」交给声明式骨架在装配之后
// 才调用的钩子。它存在的原因是两处签名约束：OperationGuard 只收进程身份、
// ConfigSync 只收 options，而 feed 并发预算来自配置快照、交集文案解析器要和
// config sync 共用同一个 HotConfigStore。骨架保证 Assemble 先于 guard 组装，
// 因此这里不需要并发保护。
type contentAPIRuntime struct {
	// hotConfigStore 必须先于 Bootstrap 存在：领域装配注册交集文案解析器时
	// 就要绑定与 config sync 循环同一个 store，否则运营态覆盖永远读不到。
	hotConfigStore *controlplane.HotConfigStore
	feed           feedRuntimeConfig
	assembled      bool
}

func newContentAPIRuntime() *contentAPIRuntime {
	return &contentAPIRuntime{hotConfigStore: controlplane.NewHotConfigStore()}
}

// guardOperations 是 content 的入站 operation 门：runtime boundary 契约判定 +
// feed 并发预算 + 敏感 operation 的主体校验。content 用 runtime boundary 而非
// public boundary——公共边界的商用状态拒绝归 api-edge。
func (runtime *contentAPIRuntime) guardOperations(servicekit.Identity) (
	func(handler http.Handler) http.Handler, error,
) {
	// 装配未跑过就没有 feed 并发预算，静默用零值等于把限流器关掉。
	if !runtime.assembled {
		return nil, errors.New(
			"content operation guard requires the domain assembly to run first",
		)
	}
	descriptors := operationsecurity.ForDomain("content")
	admissionPolicy := contentFeedAdmissionPolicy(descriptors, runtime.feed)
	return func(handler http.Handler) http.Handler {
		sensitiveOperationGuard := httpadapter.RequireSensitiveOperationPrincipal(handler)
		admissionGuard := rtgov.OperationAdmissionMiddleware(
			[]rtgov.OperationAdmissionPolicy{admissionPolicy},
			httpadapter.WriteFeedAdmissionRejection,
		)(sensitiveOperationGuard)
		return rtauth.EnforceRuntimeOperationContract(descriptors)(admissionGuard)
	}, nil
}

func contentFeedAdmissionPolicy(
	descriptors []rtauth.OperationSecurityDescriptor,
	feedConfig feedRuntimeConfig,
) rtgov.OperationAdmissionPolicy {
	operationID := ""
	for _, descriptor := range descriptors {
		if descriptor.Method != contentgenerated.RouteGetFeedMethod ||
			descriptor.PathTemplate != contentgenerated.RouteGetFeedPath {
			continue
		}
		if operationID != "" {
			panic("content feed operation descriptor is not unique")
		}
		operationID = descriptor.CanonicalOperationID
	}
	if operationID == "" {
		panic("content feed operation descriptor is missing")
	}
	return rtgov.OperationAdmissionPolicy{
		CanonicalOperationID: operationID,
		InflightLimiter:      rtgov.NewInflightLimiter(feedConfig.MaxInflight),
	}
}
