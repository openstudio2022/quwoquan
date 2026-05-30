package auth

import (
	"context"
	"net/http"
	"strings"
)

type contextKey string

const principalContextKey contextKey = "auth.principal"

// 与端云一致的可信身份请求头：中间件验签通过后，用 token principal 覆盖客户端上送值，
// 杜绝 X-Client-User-Id 被伪造。无 token 时保留原值（过渡期兼容）。
const (
	clientUserIDHeader    = "X-Client-User-Id"
	clientSubAccountIDHdr = "X-Client-Sub-Account-Id"
)

// PrincipalFromContext 读取中间件注入的可信身份。
func PrincipalFromContext(ctx context.Context) (*Claims, bool) {
	claims, ok := ctx.Value(principalContextKey).(*Claims)
	return claims, ok && claims != nil
}

// WithPrincipal 注入可信身份（测试/内部使用）。
func WithPrincipal(ctx context.Context, claims *Claims) context.Context {
	return context.WithValue(ctx, principalContextKey, claims)
}

// Middleware 解析 Authorization: Bearer，本地验签后：
//   - 将 principal 注入 context；
//   - 用 token 中的 sub/persona 覆盖 X-Client-User-Id / X-Client-Sub-Account-Id，
//     使下游 handler 的身份来自可信 token 而非客户端裸头。
//
// 不携带 token 时直接放行（public/optional 由各 operation 的 auth_mode 决定），
// 携带非法 token 时清除可信身份但不拦截（拦截策略由 RequireAuthenticated 或网关统一执行）。
func Middleware(verifier *Verifier) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if verifier == nil {
				next.ServeHTTP(w, r)
				return
			}
			token := bearerToken(r)
			if token == "" {
				next.ServeHTTP(w, r)
				return
			}
			claims, err := verifier.Verify(token)
			if err != nil {
				// 非法/过期 token：不信任其携带的裸身份头，避免越权。
				r.Header.Del(clientUserIDHeader)
				r.Header.Del(clientSubAccountIDHdr)
				next.ServeHTTP(w, r)
				return
			}
			r.Header.Set(clientUserIDHeader, claims.Subject)
			if strings.TrimSpace(claims.Persona) != "" {
				r.Header.Set(clientSubAccountIDHdr, claims.Persona)
			}
			ctx := WithPrincipal(r.Context(), claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func bearerToken(r *http.Request) string {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if header == "" {
		return ""
	}
	const prefix = "Bearer "
	if len(header) > len(prefix) && strings.EqualFold(header[:len(prefix)], prefix) {
		return strings.TrimSpace(header[len(prefix):])
	}
	return ""
}
