package http

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
)

// tag 域错误边界：code 与 http_status 以 contracts/metadata/tag/**/errors.yaml
// 为唯一真相源；响应统一走 runtime/errors 的 RuntimeErrorResponse。

const moduleTag = rterrors.ModuleTag

func tagInvalidArgument(debug string) error {
	return rterrors.NewInvalidArgument(moduleTag, "标签请求参数不正确", debug)
}

func tagNotFound(debug string) error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, rterrors.KindUser, "tag_not_found"),
		"标签不存在或已下线", debug)
	appErr.HTTPStatus = http.StatusNotFound
	return appErr
}

func tagStorageReadFailed(err error) error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, rterrors.KindSystem, "storage_read_failed"),
		"标签读取失败，请稍后重试", err.Error())
	appErr.HTTPStatus = http.StatusInternalServerError
	return appErr
}

func tagRequestIDFrom(r *http.Request) string {
	if id := strings.TrimSpace(r.Header.Get("X-Request-Id")); id != "" {
		return id
	}
	return fmt.Sprintf("tag.req.%d", time.Now().UnixNano())
}

func writeTagError(w http.ResponseWriter, r *http.Request, err error) {
	rterrors.WriteHTTPError(w, err, rterrors.HTTPWriteOptions{RequestID: tagRequestIDFrom(r)})
}
