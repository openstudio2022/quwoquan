package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

func (h *ContentHandler) handleGenerateArticleSummary(w http.ResponseWriter, r *http.Request) {
	if strings.TrimSpace(r.Header.Get("Idempotency-Key")) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"缺少幂等键",
			"GenerateArticleSummary requires Idempotency-Key",
		))
		return
	}
	payload, err := BindGeneratedRequestBodyFromRequest(r, "GenerateArticleSummary")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	title, titleOK := payload["title"].(string)
	body, bodyOK := payload["body"].(string)
	if (payload["title"] != nil && !titleOK) ||
		(payload["body"] != nil && !bodyOK) ||
		(strings.TrimSpace(title) == "" && strings.TrimSpace(body) == "") {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"标题与正文不能同时为空",
			"GenerateArticleSummary requires string title or body",
		))
		return
	}
	summary := h.postService.GenerateArticleSummary(title, body)
	writeJSON(w, http.StatusOK, map[string]any{"summary": summary})
}
