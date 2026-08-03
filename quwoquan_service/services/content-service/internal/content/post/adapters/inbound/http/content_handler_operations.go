package http

import (
	"net/http"

	rterr "quwoquan_service/runtime/errors"
)

// handleNotImplemented only serves the generated dispatch default. Operation
// ownership remains in contracts/codegen and is not re-declared here.
func (h *ContentHandler) handleNotImplemented(
	w http.ResponseWriter,
	r *http.Request,
	operation string,
) {
	writeHTTPError(w, r, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
		"接口暂未开放",
		"operation not implemented: "+operation+" "+r.Method+" "+r.URL.Path,
	))
}

func (h *ContentHandler) dispatchReport(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(ReportHTTPHandler),
) {
	if h.reportHandler == nil {
		writeHTTPError(w, r, rterr.NewUnavailable(
			rterr.ModuleContent,
			"举报服务未配置",
			"Report HTTP adapter is not configured",
		))
		return
	}
	dispatch(h.reportHandler)
}

func (h *ContentHandler) handleCreateReport(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.Create(w, r) })
}

func (h *ContentHandler) handleListReports(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.List(w, r) })
}

func (h *ContentHandler) handleListMyReports(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.ListMine(w, r) })
}

func (h *ContentHandler) handleGetReport(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.Get(w, r) })
}

func (h *ContentHandler) handleBeginReportReview(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.BeginReview(w, r) })
}

func (h *ContentHandler) handleDismissReport(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.Dismiss(w, r) })
}

func (h *ContentHandler) handleResolveReport(w http.ResponseWriter, r *http.Request) {
	h.dispatchReport(w, r, func(handler ReportHTTPHandler) { handler.Resolve(w, r) })
}
