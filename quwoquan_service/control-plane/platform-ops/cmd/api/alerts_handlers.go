package main

import (
	"crypto/subtle"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

const alertIngestTokenHeader = "X-Alert-Ingest-Token"

// requireAlertIngestToken 是 Alertmanager webhook 的专用机器凭据边界。
// 该 operation 的契约声明的是 service principal，但对侧只能携带静态 header
// token，因此它留在 generated operation guard 之外并在此 fail-closed：
// 未配置 token 直接拒绝，token 不匹配按未授权拒绝，绝不匿名放行。
func (s *platformService) requireAlertIngestToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeRuntimeNotFound(w, r)
			return
		}
		if s.alertIngestToken == "" {
			rterr.WriteHTTPError(
				w,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleOps, rterr.KindSystem, "internal_error"),
					"请求处理失败",
					"ALERT_INGEST_TOKEN is not configured",
				),
				rterr.HTTPWriteOptionsFromRequest(r),
			)
			return
		}
		provided := strings.TrimSpace(r.Header.Get(alertIngestTokenHeader))
		if subtle.ConstantTimeCompare([]byte(provided), []byte(s.alertIngestToken)) != 1 {
			rterr.WriteHTTPError(
				w,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
					"请先登录",
					"alert ingest token mismatch",
				),
				rterr.HTTPWriteOptionsFromRequest(r),
			)
			return
		}
		next.ServeHTTP(w, r)
	})
}
