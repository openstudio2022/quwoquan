package http

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	auth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/user-service/generated/account/user_account"
	authority "quwoquan_service/services/user-service/internal/account/user_account/application"
	"time"
)

type CollectionQueryAuthorityHandler struct {
	authority *authority.CollectionQueryAuthority
}

func NewCollectionQueryAuthorityHandler(a *authority.CollectionQueryAuthority) *CollectionQueryAuthorityHandler {
	if a == nil {
		panic("collection query authority missing")
	}
	return &CollectionQueryAuthorityHandler{a}
}
func (h *CollectionQueryAuthorityHandler) RegisterRoutes(mux *http.ServeMux) {
	for _, d := range operationsecurity.ForDomain("user") {
		switch d.CanonicalOperationID {
		case "user.user_account.IssueCollectionQueryGrant":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.issue)
		case "user.user_account.VerifyCollectionQueryGrant":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.verify)
		}
	}
}
func authorityDecode(w http.ResponseWriter, r *http.Request, dst any) bool {
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 32768))
	d.DisallowUnknownFields()
	if d.Decode(dst) != nil {
		return false
	}
	var extra any
	return d.Decode(&extra) == io.EOF
}
func authorityError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
func authorityResult(w http.ResponseWriter, result any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(result)
}
func (h *CollectionQueryAuthorityHandler) issue(w http.ResponseWriter, r *http.Request) {
	caller, ok := auth.PrincipalFromContext(r.Context())
	if !ok {
		authorityError(w, r, generated.AppErrorFromCollectionQueryDenied(""))
		return
	}
	var in struct {
		SourceAccessToken string                           `json:"sourceAccessToken"`
		Binding           authority.CollectionQueryBinding `json:"binding"`
	}
	if !authorityDecode(w, r, &in) {
		authorityError(w, r, generated.AppErrorFromCollectionQueryDenied(""))
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 800*time.Millisecond)
	defer cancel()
	result, err := h.authority.Issue(ctx, caller, in.SourceAccessToken, in.Binding)
	if err != nil {
		authorityError(w, r, err)
		return
	}
	authorityResult(w, result)
}
func (h *CollectionQueryAuthorityHandler) verify(w http.ResponseWriter, r *http.Request) {
	caller, ok := auth.PrincipalFromContext(r.Context())
	if !ok {
		authorityError(w, r, generated.AppErrorFromCollectionQueryDenied(""))
		return
	}
	var in struct {
		Grant   string                           `json:"grant"`
		Binding authority.CollectionQueryBinding `json:"binding"`
	}
	if !authorityDecode(w, r, &in) {
		authorityError(w, r, generated.AppErrorFromCollectionQueryDenied(""))
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 800*time.Millisecond)
	defer cancel()
	result, err := h.authority.Verify(ctx, caller, in.Grant, in.Binding)
	if err != nil {
		authorityError(w, r, err)
		return
	}
	authorityResult(w, result)
}
