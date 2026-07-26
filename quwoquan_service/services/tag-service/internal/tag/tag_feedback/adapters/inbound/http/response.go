package httpadapter

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
)

const moduleTag = rterrors.ModuleTag

func tagInvalidArgument(debug string) error {
	return rterrors.NewInvalidArgument(moduleTag, "标签请求参数不正确", debug)
}

func tagNotFound(debug string) error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, rterrors.KindUser, "tag_not_found"),
		"标签不存在或已下线", debug,
	)
	appErr.HTTPStatus = http.StatusNotFound
	return appErr
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeTagError(w http.ResponseWriter, r *http.Request, err error) {
	requestID := strings.TrimSpace(r.Header.Get("X-Request-Id"))
	if requestID == "" {
		requestID = fmt.Sprintf("tag.feedback.req.%d", time.Now().UnixNano())
	}
	rterrors.WriteHTTPError(w, err, rterrors.HTTPWriteOptions{RequestID: requestID})
}
