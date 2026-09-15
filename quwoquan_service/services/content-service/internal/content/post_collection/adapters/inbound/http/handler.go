package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/post_collection"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
)

// Handler 只接收已验证 principal；不能从 payload 或自定义 header 获取 owner。
type Handler struct{ Service *app.Service }

func (h Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc(generated.RouteSavePostCollectionMethod+" "+generated.RouteSavePostCollectionPath, h.Save)
	mux.HandleFunc(generated.RouteDeletePostCollectionMethod+" "+generated.RouteDeletePostCollectionPath, h.Delete)
}
func actor(r *http.Request) string {
	p, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ""
	}
	return p.Actor.PersonaID
}
func decode(w http.ResponseWriter, r *http.Request, dst any) error {
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 256*1024))
	d.DisallowUnknownFields()
	if d.Decode(dst) != nil {
		return domain.Invalid
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return domain.Invalid
	}
	return nil
}
func reply(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(value)
}
func failure(w http.ResponseWriter, r *http.Request, err error) {
	var mapped error
	switch {
	case errors.Is(err, domain.Invalid):
		mapped = generated.AppErrorFromPostCollectionInvalidArgument("")
	case errors.Is(err, domain.Unauthorized):
		mapped = generated.AppErrorFromPostCollectionUnauthorized("")
	case errors.Is(err, domain.Conflict):
		mapped = generated.AppErrorFromPostCollectionVersionConflict("")
	case errors.Is(err, domain.Unavailable):
		mapped = generated.AppErrorFromPostCollectionUnavailable("")
	case errors.Is(err, domain.StorageWrite):
		mapped = generated.AppErrorFromPostCollectionWriteFailed("")
	default:
		mapped = generated.AppErrorFromPostCollectionReadFailed("")
	}
	rterr.WriteHTTPError(w, mapped, rterr.HTTPWriteOptionsFromRequest(r))
}
func (h Handler) Save(w http.ResponseWriter, r *http.Request) {
	if h.Service == nil {
		failure(w, r, domain.StorageWrite)
		return
	}
	if actor(r) == "" {
		failure(w, r, domain.Unauthorized)
		return
	}
	var in struct {
		CollectionID    string            `json:"collectionId"`
		ExpectedVersion *int64            `json:"expectedVersion"`
		Name            string            `json:"name"`
		CoverAssetID    *string           `json:"coverAssetId"`
		Visibility      domain.Visibility `json:"visibility"`
		PostIDs         *[]string         `json:"postIds"`
	}
	if decode(w, r, &in) != nil || in.ExpectedVersion == nil || in.PostIDs == nil || (in.CollectionID != "" && in.CollectionID != r.PathValue("collectionId")) {
		failure(w, r, domain.Invalid)
		return
	}
	cover := ""
	if in.CoverAssetID != nil {
		cover = *in.CoverAssetID
	}
	out, err := h.Service.Save(r.Context(), actor(r), domain.Save{ID: r.PathValue("collectionId"), ExpectedVersion: *in.ExpectedVersion, Name: in.Name, CoverAssetID: cover, Visibility: in.Visibility, PostIDs: *in.PostIDs})
	if err != nil {
		failure(w, r, err)
		return
	}
	reply(w, out)
}
func (h Handler) Delete(w http.ResponseWriter, r *http.Request) {
	if h.Service == nil {
		failure(w, r, domain.StorageWrite)
		return
	}
	if actor(r) == "" {
		failure(w, r, domain.Unauthorized)
		return
	}
	var in struct {
		CollectionID    string `json:"collectionId"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if decode(w, r, &in) != nil || in.ExpectedVersion == nil || (in.CollectionID != "" && in.CollectionID != r.PathValue("collectionId")) {
		failure(w, r, domain.Invalid)
		return
	}
	out, err := h.Service.Delete(r.Context(), actor(r), r.PathValue("collectionId"), *in.ExpectedVersion)
	if err != nil {
		failure(w, r, err)
		return
	}
	reply(w, out)
}