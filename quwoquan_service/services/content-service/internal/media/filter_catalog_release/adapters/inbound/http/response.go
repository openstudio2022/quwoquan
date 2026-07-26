package http

import (
	"encoding/json"
	"net/http"

	rterr "quwoquan_service/runtime/errors"
)

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(
	writer http.ResponseWriter,
	request *http.Request,
	err error,
) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
