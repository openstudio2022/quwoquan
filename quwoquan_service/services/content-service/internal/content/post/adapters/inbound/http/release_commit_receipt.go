package http

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/post"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"time"
)

type ReleaseCommitReceiptHandler struct {
	facade      *app.ContentReleaseCommitReceiptQueryFacade
	environment string
}

func NewReleaseCommitReceiptHandler(reader app.ContentReleaseCommitReceiptReader, environment string) *ReleaseCommitReceiptHandler {
	return &ReleaseCommitReceiptHandler{app.NewContentReleaseCommitReceiptQueryFacade(reader), environment}
}
func (h *ReleaseCommitReceiptHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc(generated.RouteReadContentReleaseCommitReceiptMethod+" "+generated.RouteReadContentReleaseCommitReceiptPath, h.read)
}
func (h *ReleaseCommitReceiptHandler) read(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(io.LimitReader(r.Body, 32769))
	var q wire.ReadContentReleaseCommitReceiptQuery
	if err == nil && len(raw) <= 32768 {
		dec := json.NewDecoder(bytes.NewReader(raw))
		dec.DisallowUnknownFields()
		err = dec.Decode(&q)
		if err == nil {
			if dec.Decode(&struct{}{}) != io.EOF {
				err = app.ErrReleaseQueryInvalid
			}
		}
	} else {
		err = app.ErrReleaseQueryInvalid
	}
	// bool/0/null也须明确出现在请求，不能让Go零值补造expected-empty。
	var root map[string]json.RawMessage
	if err == nil {
		err = json.Unmarshal(raw, &root)
	}
	for section, keys := range map[string][]string{"release": {"environment", "sourceOwner", "releaseId", "manifestDigest"}, "expected": {"found", "environment", "sourceOwner", "releaseId", "manifestDigest", "revision", "projectionVersion", "activatedAt"}} {
		var fields map[string]json.RawMessage
		if json.Unmarshal(root[section], &fields) != nil {
			err = app.ErrReleaseQueryInvalid
		}
		for _, key := range keys {
			v, ok := fields[key]
			if !ok || (key != "activatedAt" && bytes.Equal(bytes.TrimSpace(v), []byte("null"))) {
				err = app.ErrReleaseQueryInvalid
			}
		}
	}
	if err != nil || q.Release.Environment != h.environment || q.Release.SourceOwner != "qwq_data" {
		rterr.WriteHTTPError(w, generated.AppErrorFromContentReleaseQueryBarrierInvalid("invalid exact commit query"), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 500*time.Millisecond)
	defer cancel()
	receipt, err := h.facade.Read(ctx, q)
	if err != nil {
		failure := generated.AppErrorFromContentReleaseQueryBarrierUnavailable("commit receipt unavailable")
		if errors.Is(err, app.ErrReleaseQueryNotReady) {
			failure = generated.AppErrorFromContentReleaseQueryBarrierNotReady("commit receipt not ready")
		}
		if errors.Is(err, app.ErrReleaseQueryInvalid) {
			failure = generated.AppErrorFromContentReleaseQueryBarrierInvalid("commit receipt identity conflict")
		}
		rterr.WriteHTTPError(w, failure, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(receipt)
}
