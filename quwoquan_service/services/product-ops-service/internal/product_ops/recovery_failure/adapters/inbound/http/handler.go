package httpadapter

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	recoverygenerated "quwoquan_service/services/product-ops-service/generated/product_ops/recovery_failure"
	"quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
)

const maxRecoveryFailureBytes = 40 << 10

type ErrorWriter func(http.ResponseWriter, *http.Request, int, string, string)

// Handler 只做载荷校验与应用调用。匿名来源的权威准入由 api-edge 的共享
// admission（rate_limit.operation.ops_recovery_failure_report，subject 为
// 可信连接层 IP）跨副本裁决；进程内窗口限流已退役——它的窗口状态只存在于
// 单副本内存，多副本下准入上限随副本数放大，不构成准入保证。
type Handler struct {
	service    *application.Service
	writeError ErrorWriter
}

func NewHandler(service *application.Service, writeError ErrorWriter) *Handler {
	return &Handler{service: service, writeError: writeError}
}

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ops/recovery-failures", h.report)
}

func (h *Handler) report(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		h.writeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
		return
	}
	if h.service == nil {
		h.writeAppError(w, r, recoverygenerated.AppErrorFromRecoveryFailureUnavailable("recovery failure service unavailable"))
		return
	}
	var failure application.Failure
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxRecoveryFailureBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&failure); err != nil {
		h.writeAppError(w, r, recoverygenerated.AppErrorFromRecoveryFailureInvalid(err.Error()))
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		h.writeAppError(w, r, recoverygenerated.AppErrorFromRecoveryFailureInvalid("request body must contain exactly one JSON object"))
		return
	}
	if err := h.service.Report(r.Context(), failure); err != nil {
		if errors.Is(err, application.ErrInvalidRecoveryFailure) {
			h.writeAppError(w, r, recoverygenerated.AppErrorFromRecoveryFailureInvalid(err.Error()))
			return
		}
		h.writeAppError(w, r, recoverygenerated.AppErrorFromRecoveryFailureUnavailable(err.Error()))
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) writeAppError(w http.ResponseWriter, r *http.Request, err *rterr.AppError) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
