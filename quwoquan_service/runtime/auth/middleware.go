package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
)

type contextKey string

const (
	principalContextKey contextKey = "auth.principal"
	DeviceTicketHeader             = "X-Device-Ticket"
)

// 与端云一致的可信身份请求头：中间件先清除客户端上送值，验签通过后再由
// token principal 重建，防止任何下游从裸 header 构造可信 ActorContext。
const (
	clientUserIDHeader    = "X-Client-User-Id"
	clientSubAccountIDHdr = "X-Client-Sub-Account-Id"
	clientAccountIDHeader = "X-Client-Account-Id"
	clientPersonaIDHeader = "X-Client-Persona-Id"
	clientDeviceActorHdr  = "X-Client-Device-Actor-Id"
	untrustedUserIDHeader = "X-User-Id"
	untrustedActorHeader  = "X-Actor"
)

type Principal struct {
	Claims
	Actor operation.ActorContext
}

func PrincipalFromContext(ctx context.Context) (Principal, bool) {
	principal, ok := ctx.Value(principalContextKey).(Principal)
	return principal, ok
}

// WithPrincipal 仅用于测试和内部 transport；调用方必须传入已验证 principal。
func WithPrincipal(ctx context.Context, principal Principal) context.Context {
	return context.WithValue(ctx, principalContextKey, principal)
}

type MiddlewareConfig struct {
	AccessTokenVerifier  *Verifier
	DeviceTicketVerifier *Verifier
}

// Middleware 永远先清除客户端身份头，再从唯一 credential 重建可信 Principal。
// 无 credential 的请求继续交给 operation guard 判断 public/optional；只要客户端
// 提供了非法或冲突 credential，就立即返回结构化 401，禁止降级成匿名请求。
func Middleware(config MiddlewareConfig) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			clearClientIdentityHeaders(r.Header)
			accessToken, accessSupplied := bearerToken(r)
			deviceTicket := strings.TrimSpace(r.Header.Get(DeviceTicketHeader))
			r.Header.Del("Authorization")
			r.Header.Del(DeviceTicketHeader)
			if accessSupplied && deviceTicket != "" {
				writeCredentialError(w, r, ErrInvalidToken)
				return
			}
			if !accessSupplied && deviceTicket == "" {
				next.ServeHTTP(w, r)
				return
			}
			var (
				claims *Claims
				err    error
			)
			if accessSupplied {
				if accessToken == "" || config.AccessTokenVerifier == nil {
					writeCredentialError(w, r, ErrInvalidToken)
					return
				}
				claims, err = config.AccessTokenVerifier.Verify(accessToken)
			} else {
				if config.DeviceTicketVerifier == nil {
					writeCredentialError(w, r, ErrInvalidToken)
					return
				}
				claims, err = config.DeviceTicketVerifier.Verify(deviceTicket)
			}
			if err != nil {
				writeCredentialError(w, r, err)
				return
			}
			principal := principalFromClaims(*claims)
			applyTrustedIdentityHeaders(r.Header, principal.Actor)
			ctx := WithPrincipal(r.Context(), principal)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func principalFromClaims(claims Claims) Principal {
	actor := operation.ActorContext{}
	switch claims.TokenType {
	case TokenTypeAccess:
		actor.AccountID = strings.TrimSpace(claims.Subject)
		actor.PersonaID = strings.TrimSpace(claims.Persona)
	case TokenTypeDevice:
		actor.DeviceActorID = strings.TrimSpace(claims.DeviceActorID)
	}
	return Principal{Claims: claims, Actor: actor}
}

func applyTrustedIdentityHeaders(headers http.Header, actor operation.ActorContext) {
	if actor.AccountID != "" {
		headers.Set(clientUserIDHeader, actor.AccountID)
		headers.Set(clientAccountIDHeader, actor.AccountID)
	}
	if actor.PersonaID != "" {
		headers.Set(clientSubAccountIDHdr, actor.PersonaID)
		headers.Set(clientPersonaIDHeader, actor.PersonaID)
	}
	if actor.DeviceActorID != "" {
		headers.Set(clientDeviceActorHdr, actor.DeviceActorID)
	}
}

func writeCredentialError(w http.ResponseWriter, r *http.Request, cause error) {
	reason := "unauthorized"
	debugMessage := "credential verification failed"
	if errors.Is(cause, ErrExpiredToken) {
		reason = "token_expired"
		debugMessage = "credential expired"
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, rterr.KindUser, reason),
			"请先登录",
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func bearerToken(r *http.Request) (string, bool) {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if header == "" {
		return "", false
	}
	const prefix = "Bearer "
	if len(header) > len(prefix) && strings.EqualFold(header[:len(prefix)], prefix) {
		return strings.TrimSpace(header[len(prefix):]), true
	}
	return "", true
}

func clearClientIdentityHeaders(headers http.Header) {
	headers.Del(clientUserIDHeader)
	headers.Del(clientSubAccountIDHdr)
	headers.Del(clientAccountIDHeader)
	headers.Del(clientPersonaIDHeader)
	headers.Del(clientDeviceActorHdr)
	headers.Del(untrustedUserIDHeader)
	headers.Del(untrustedActorHeader)
}
