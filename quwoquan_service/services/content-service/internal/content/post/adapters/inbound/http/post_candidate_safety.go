package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/post"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/safety"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
)

func RegisterPostCandidateSafety(mux *http.ServeMux, reader app.PostCandidateSafetyReader) {
	facade := app.NewPostCandidateSafetyQueryFacade(reader)
	mux.HandleFunc(generated.RouteReadPostCandidateSafetyMethod+" "+generated.RouteReadPostCandidateSafetyPath, func(w http.ResponseWriter, r *http.Request) {
		var q wire.ReadPostCandidateSafetyQuery
		dec := json.NewDecoder(io.LimitReader(r.Body, 16385))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&q); err != nil || dec.Decode(&struct{}{}) != io.EOF {
			rterr.WriteHTTPError(w, generated.AppErrorFromContentReleaseQueryBarrierInvalid("invalid Post safety query"), rterr.HTTPWriteOptionsFromRequest(r))
			return
		}
		value, err := facade.Read(r.Context(), q)
		if err != nil {
			failure := generated.AppErrorFromContentReleaseQueryBarrierUnavailable("Post safety authority unavailable")
			if errors.Is(err, app.ErrPostSafetyNotReady) {
				failure = generated.AppErrorFromContentReleaseQueryBarrierNotReady("Post safety not ready")
			}
			if errors.Is(err, app.ErrPostSafetyConflict) {
				failure = generated.AppErrorFromContentReleaseQueryBarrierInvalid("Post safety identity differs")
			}
			rterr.WriteHTTPError(w, failure, rterr.HTTPWriteOptionsFromRequest(r))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		_ = json.NewEncoder(w).Encode(value)
	})
}
