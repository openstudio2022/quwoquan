package http

import (
	"errors"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const closeAccountOperationID = "user.user_profile.CloseAccount"

// enforceAccountSecurity 在认证之后、业务 Handler 之前读取 UserAccount 的权威状态。
// 用户凭证无法核验状态或 authEpoch 时 fail-closed；服务、运营与设备 principal 不属于
// 终端用户账号，仍由 generated operation guard 依据 metadata 单独校验。
func (h *UserHandler) enforceAccountSecurity(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		principal, hasPrincipal := rtauth.PrincipalFromContext(r.Context())
		if !hasPrincipal || !isEndUserAccountPrincipal(principal) {
			next.ServeHTTP(w, r)
			return
		}
		if h.accountSecurity == nil {
			writeHTTPError(w, r, generated.AppErrorFromInternalError(
				"UserAccount security reader is unavailable",
			))
			return
		}
		snapshot, err := h.accountSecurity.ReadAccountSecurity(
			r.Context(),
			principal.Actor.AccountID,
		)
		if errors.Is(err, accountports.ErrAccountNotFound) {
			writeHTTPError(w, r, generated.AppErrorFromUserNotFound(
				"authenticated account no longer exists",
			))
			return
		}
		if err != nil {
			writeHTTPError(w, r, generated.AppErrorFromInternalError(
				"UserAccount security state is unavailable",
			))
			return
		}
		switch strings.TrimSpace(snapshot.AccountState) {
		case "suspended":
			writeHTTPError(w, r, generated.AppErrorFromAccountSuspended(
				"authenticated account is suspended",
			))
			return
		case "closed":
			if invocation, ok := operation.FromContext(r.Context()); ok &&
				invocation.OperationID == closeAccountOperationID {
				// CloseAccount 的 metadata 契约要求 closed 终态重放返回幂等成功。
				// 仅放行该 canonical operation；其余请求仍在业务 Handler 前拒绝。
				next.ServeHTTP(w, r)
				return
			}
			writeHTTPError(w, r, generated.AppErrorFromAccountDeleted(
				"authenticated account is closed",
			))
			return
		case "active", "anonymous":
			// 继续进行 authEpoch 校验。
		default:
			writeHTTPError(w, r, generated.AppErrorFromInternalError(
				"UserAccount security state is invalid",
			))
			return
		}
		if principal.AuthEpoch <= 0 || principal.AuthEpoch != snapshot.AuthEpoch {
			writeHTTPError(w, r, generated.AppErrorFromUnauthorized(
				"authenticated token security epoch is stale",
			))
			return
		}
		next.ServeHTTP(w, r)
	})
}

func isEndUserAccountPrincipal(principal rtauth.Principal) bool {
	if strings.TrimSpace(principal.Actor.AccountID) == "" {
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
