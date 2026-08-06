package main

import (
	"crypto/subtle"
	"net/http"
	"os"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
)

func writeControlPlaneUnauthorized(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
			"请先登录",
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

const alertIngestTokenHeader = "X-Alert-Ingest-Token"

// requireControlPlanePrincipal 是控制面对象完成 ContractGraph 登记前的迁移期
// 底线：除 Alertmanager ingest（以专用 token 认证的机器推送）外，任何控制面
// 路径都必须携带已验证 principal，禁止匿名触达。
func requireControlPlanePrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/control-plane/platform/alerts/ingest" {
			expected := strings.TrimSpace(os.Getenv("ALERT_INGEST_TOKEN"))
			if expected == "" {
				writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", "ALERT_INGEST_TOKEN is not configured")
				return
			}
			provided := strings.TrimSpace(r.Header.Get(alertIngestTokenHeader))
			if subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
				writeControlPlaneUnauthorized(w, r, "alert ingest token mismatch")
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		if _, ok := rtauth.PrincipalFromContext(r.Context()); !ok {
			writeControlPlaneUnauthorized(w, r, "verified operator principal is required")
			return
		}
		next.ServeHTTP(w, r)
	})
}
