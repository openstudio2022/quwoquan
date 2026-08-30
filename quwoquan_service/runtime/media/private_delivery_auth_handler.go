package runtimemedia

import (
	"net/http"
	"net/url"
	"time"
)

// NewPrivateDeliveryAuthHandler 构造边缘 forward_auth 的验签端点
// （DEC-031 网络层边缘守卫）：Caddy 等边缘对私有交付前缀把原始请求
// URI 经 X-Forwarded-Uri 转发到这里，由共享 verifier 复算 HMAC 签名
// 与绝对到期。判定为纯 CPU 复算，不触任何存储或下游。
//
// 语义：非私有前缀一律 204（该端点不评判公开面）；私有前缀验签通过
// 204，否则 403。signKey 缺失时私有前缀整体 fail closed。
func NewPrivateDeliveryAuthHandler(
	signKey string,
	now func() time.Time,
) http.Handler {
	if now == nil {
		now = time.Now
	}
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		forwardedURI := request.Header.Get("X-Forwarded-Uri")
		if forwardedURI == "" {
			// 无边缘转发上下文的直接访问没有可判定对象。
			http.Error(writer, "missing X-Forwarded-Uri", http.StatusForbidden)
			return
		}
		parsed, err := url.ParseRequestURI(forwardedURI)
		if err != nil {
			http.Error(writer, "malformed forwarded uri", http.StatusForbidden)
			return
		}
		if !IsPrivateDeliveryPath(parsed.EscapedPath()) {
			writer.WriteHeader(http.StatusNoContent)
			return
		}
		query := parsed.Query()
		if !VerifyPrivateDeliverySignature(
			parsed.EscapedPath(),
			query.Get("sign"),
			query.Get("t"),
			signKey,
			now(),
		) {
			http.Error(
				writer,
				"private media delivery requires a valid signed URL",
				http.StatusForbidden,
			)
			return
		}
		writer.WriteHeader(http.StatusNoContent)
	})
}
