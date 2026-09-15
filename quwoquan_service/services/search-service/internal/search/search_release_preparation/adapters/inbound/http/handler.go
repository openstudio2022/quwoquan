package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/search-service/generated/search/search_release_preparation"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	"slices"
	"strings"
	"time"
)

type Handler struct{ service *application.Service }

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("preparation service required")
	}
	return &Handler{service}
}
func (h *Handler) Register(mux *http.ServeMux) {
	for _, d := range operationsecurity.ForDomain("search") {
		switch d.CanonicalOperationID {
		case "search.search_release_preparation.PrepareSearchRelease":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.prepare)
		case "search.search_release_preparation.ReadSearchReleasePreparation":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.read)
		}
	}
}
func forbidden() *rterr.AppError {
	code, _ := rterr.ParseCode("GATEWAY.USER.forbidden")
	return rterr.NewAppError(code, "当前账号没有该操作权限", "verified content principal required").WithMetadata("forbidden", 403).WithRecoveryDirective("surface", "inlineCard", 0)
}

func permitted(r *http.Request, scope string) bool {
	p, ok := auth.PrincipalFromContext(r.Context())
	return ok && p.TokenType == auth.TokenTypeAccess &&
		p.Actor.AccountID == "service:content-service" && p.ServiceActorID == "" &&
		p.Actor.PersonaID == "" && slices.Contains(p.Roles, "service") &&
		slices.Contains(strings.Fields(p.Scope), scope)
}
func (h *Handler) prepare(w http.ResponseWriter, r *http.Request) {
	if !permitted(r, "search.release.prepare") {
		rterr.WriteHTTPError(w, forbidden(), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	var command domain.Command
	if err := rt.DecodeCreatorValue(r.Body, &command); err != nil {
		writeFailure(w, r, domain.ErrInvalid)
		return
	}
	invocation, ok := operation.FromContext(r.Context())
	if !ok || invocation.IdempotencyKey == "" || command.IdempotencyKey != invocation.IdempotencyKey {
		writeFailure(w, r, domain.ErrInvalid)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	view, err := h.service.Prepare(ctx, command, "content-service")
	respond(w, r, view, err)
}
func (h *Handler) read(w http.ResponseWriter, r *http.Request) {
	if !permitted(r, "search.release.read") {
		rterr.WriteHTTPError(w, forbidden(), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	var query domain.Query
	if err := rt.DecodeCreatorValue(r.Body, &query); err != nil {
		writeFailure(w, r, domain.ErrInvalid)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	view, err := h.service.Read(ctx, query)
	respond(w, r, view, err)
}
func respond(w http.ResponseWriter, r *http.Request, view domain.View, err error) {
	if err != nil {
		writeFailure(w, r, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(view)
}
func writeFailure(w http.ResponseWriter, r *http.Request, err error) {
	failure := generated.AppErrorFromSearchPreparationUnavailable("preparation dependency failed")
	switch {
	case errors.Is(err, domain.ErrInvalid):
		failure = generated.AppErrorFromSearchPreparationInvalidInput("invalid preparation value")
	case errors.Is(err, domain.ErrConflict):
		failure = generated.AppErrorFromSearchPreparationConflict("preparation binding or checkpoint conflict")
	case errors.Is(err, domain.ErrNotFound):
		failure = generated.AppErrorFromSearchPreparationNotFound("exact preparation absent")
	}
	rterr.WriteHTTPError(w, failure, rterr.HTTPWriteOptionsFromRequest(r))
}
