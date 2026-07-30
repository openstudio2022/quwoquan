package auth

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

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
	OperatorOIDCVerifier *OIDCVerifier
	// AccountSecurityAuthority is intentionally optional only for transports
	// that do not accept end-user access JWTs (for example user-service's
	// direct PostgreSQL authority gate). Every resource-service composition
	// that accepts end-user access JWTs must supply it and fail startup if it
	// cannot be constructed.
	AccountSecurityAuthority AccountSecurityAuthority
	// AccountSecurityExemption is constrained to an already-confirmed closed
	// state and exists only for a canonical idempotent terminal command (the
	// UserAccount close replay). It must never be used for active, suspended,
	// stale, unavailable, service, operator, or device principals.
	AccountSecurityExemption AccountSecurityExemption
}

// AccountSecurityExemption allows a caller to retain one explicit terminal
// operation's replay semantics after the authority has confirmed closed. It
// receives no token material and cannot turn an authority failure into allow.
type AccountSecurityExemption func(
	request *http.Request,
	principal Principal,
	snapshot AccountSecuritySnapshot,
) bool

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
				if accessToken == "" {
					writeCredentialError(w, r, ErrInvalidToken)
					return
				}
				if config.AccessTokenVerifier != nil {
					claims, err = config.AccessTokenVerifier.Verify(accessToken)
				} else {
					err = ErrInvalidToken
				}
				if err != nil && config.OperatorOIDCVerifier != nil && looksLikeRS256JWT(accessToken) {
					operatorPrincipal, operatorErr := config.OperatorOIDCVerifier.Verify(accessToken)
					if operatorErr == nil {
						principal := operatorPrincipal
						applyTrustedIdentityHeaders(r.Header, principal.Actor)
						ctx := WithPrincipal(r.Context(), principal)
						next.ServeHTTP(w, r.WithContext(ctx))
						return
					}
					err = operatorErr
				}
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
			r = r.WithContext(
				withAccountSecurityAuthorityCorrelation(r.Context(), r.Header),
			)
			if denied := enforceAccountSecurityAuthority(
				r,
				principal,
				config.AccountSecurityAuthority,
				config.AccountSecurityExemption,
			); denied != "" {
				writeAccountSecurityCredentialError(w, r, denied)
				return
			}
			applyTrustedIdentityHeaders(r.Header, principal.Actor)
			ctx := WithPrincipal(r.Context(), principal)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func looksLikeRS256JWT(token string) bool {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 3 {
		return false
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return false
	}
	var header struct {
		Alg string `json:"alg"`
	}
	return json.Unmarshal(raw, &header) == nil && header.Alg == "RS256"
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
	} else if errors.Is(cause, ErrOIDCNotMFA) {
		reason = "mfa_required"
		debugMessage = "operator mfa is required"
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

type accountSecurityDenyReason string

const (
	accountSecurityDeniedDeleted     accountSecurityDenyReason = "deleted"
	accountSecurityDeniedSuspended   accountSecurityDenyReason = "suspended"
	accountSecurityDeniedTokenStale  accountSecurityDenyReason = "token_stale"
	accountSecurityDeniedUnavailable accountSecurityDenyReason = "unavailable"
)

func enforceAccountSecurityAuthority(
	request *http.Request,
	principal Principal,
	authority AccountSecurityAuthority,
	exemption AccountSecurityExemption,
) accountSecurityDenyReason {
	if authority == nil || !requiresAccountSecurityAuthority(principal) {
		return ""
	}
	startedAt := time.Now()
	snapshot, err := authority.ReadAccountSecurity(
		request.Context(),
		principal.Actor.AccountID,
	)
	if errors.Is(err, ErrAccountSecurityNotFound) {
		recordAccountSecurityAuthorityCheck("denied_deleted", startedAt)
		return accountSecurityDeniedDeleted
	}
	if err != nil {
		recordAccountSecurityAuthorityCheck("unavailable", startedAt)
		return accountSecurityDeniedUnavailable
	}
	switch strings.TrimSpace(snapshot.AccountState) {
	case "closed":
		if exemption != nil && exemption(request, principal, snapshot) {
			recordAccountSecurityAuthorityCheck("allowed_terminal_replay", startedAt)
			return ""
		}
		recordAccountSecurityAuthorityCheck("denied_deleted", startedAt)
		return accountSecurityDeniedDeleted
	case "suspended":
		recordAccountSecurityAuthorityCheck("denied_suspended", startedAt)
		return accountSecurityDeniedSuspended
	case "active", "anonymous":
		if principal.AuthEpoch <= 0 || principal.AuthEpoch != snapshot.AuthEpoch {
			recordAccountSecurityAuthorityCheck("denied_token_stale", startedAt)
			return accountSecurityDeniedTokenStale
		}
		recordAccountSecurityAuthorityCheck("allowed", startedAt)
		return ""
	default:
		recordAccountSecurityAuthorityCheck("unavailable", startedAt)
		return accountSecurityDeniedUnavailable
	}
}

func requiresAccountSecurityAuthority(principal Principal) bool {
	if principal.TokenType != TokenTypeAccess ||
		strings.TrimSpace(principal.Actor.AccountID) == "" {
		return false
	}
	for _, role := range principal.Roles {
		switch strings.TrimSpace(role) {
		case "service", "operator", "admin":
			return false
		}
	}
	return true
}

func writeAccountSecurityCredentialError(
	w http.ResponseWriter,
	r *http.Request,
	reason accountSecurityDenyReason,
) {
	var appError *rterr.AppError
	authKind := rterr.Kind("AUTH")
	switch reason {
	case accountSecurityDeniedDeleted:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, authKind, "account_deleted"),
			"账号已注销或进入删除流程，请更换手机号登录",
			"account security authority denied the credential",
		).WithMetadata("deleted", http.StatusGone).
			WithRecoveryDirective("escalate", "inlineCard", 0)
	case accountSecurityDeniedSuspended:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, authKind, "account_suspended"),
			"账号已被限制登录，请更换手机号或联系支持",
			"account security authority denied the credential",
		).WithMetadata("suspended", http.StatusForbidden).
			WithRecoveryDirective("escalate", "inlineCard", 0)
	case accountSecurityDeniedTokenStale:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, authKind, "token_stale"),
			"登录凭据已失效，请重新登录",
			"account security authority rejected a stale credential",
		).WithMetadata("token_stale", http.StatusUnauthorized).
			WithRecoveryDirective("surface", "inlineCard", 0)
	default:
		appError = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, authKind, "account_security_unavailable"),
			"账号安全校验暂不可用，请稍后重试",
			"account security authority is unavailable",
		).WithMetadata("account_security_unavailable", http.StatusServiceUnavailable).
			WithRecoveryDirective("retry", "inlineCard", 3)
	}
	rterr.WriteHTTPError(w, appError, rterr.HTTPWriteOptionsFromRequest(r))
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
	headers.Del(clientAccountIDHeader)
	headers.Del(clientPersonaIDHeader)
	headers.Del(clientDeviceActorHdr)
	headers.Del(untrustedUserIDHeader)
	headers.Del(untrustedActorHeader)
}
