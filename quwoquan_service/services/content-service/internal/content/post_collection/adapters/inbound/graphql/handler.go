package graphql

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	auth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/post_collection"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	"strings"
	"time"
)

const ReadHash = "aabadb9772a276ea6c2837d0b04508e7fcbb1d8be5d6194e01ba837a6dee0f5a"
const ManagementHash = "a57f5fda7db3268872328cb520504de42bd12fe34e97bff61d804674b112d4db"
const Scope = "content.post_collection.graphql.read"

type Authority interface {
	Verify(context.Context, string, auth.CollectionQueryBinding) (auth.VerifiedCollectionQueryIdentity, error)
}
type Handler struct {
	Service   *app.Service
	Authority Authority
	GraphHash string
	Next      http.Handler
}
type payload struct {
	OperationName string `json:"operationName"`
	Variables     struct {
		CollectionID string  `json:"collectionId"`
		First        *int    `json:"first,omitempty"`
		After        *string `json:"after,omitempty"`
	} `json:"variables"`
	Extensions struct {
		PersistedQuery struct {
			Version int    `json:"version"`
			Hash    string `json:"sha256Hash"`
		} `json:"persistedQuery"`
	} `json:"extensions"`
}

func (h Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(io.LimitReader(r.Body, 32769))
	if err != nil || len(raw) > 32768 {
		fail(w, r, domain.Invalid)
		return
	}
	var marker struct {
		OperationName string `json:"operationName"`
	}
	if json.Unmarshal(raw, &marker) != nil {
		fail(w, r, domain.Invalid)
		return
	}
	if marker.OperationName != "PostCollection" && marker.OperationName != "PostCollectionManagement" {
		if h.Next != nil {
			r.Body = io.NopCloser(bytes.NewReader(raw))
			h.Next.ServeHTTP(w, r)
		} else {
			fail(w, r, domain.Invalid)
		}
		return
	}
	mt, _, e := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if e != nil || mt != "application/json" || r.Method != "POST" || r.URL.Path != "/internal/graphql" || r.Header.Get("X-Contract-Graph-SHA256") != h.GraphHash {
		fail(w, r, domain.Invalid)
		return
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var p payload
	var extra any
	if decoder.Decode(&p) != nil || decoder.Decode(&extra) != io.EOF || p.Variables.CollectionID == "" {
		fail(w, r, domain.Invalid)
		return
	}
	expectedHash := ReadHash
	operation := "content.post_collection.GetPostCollection"
	root := "postCollection"
	if p.OperationName == "PostCollectionManagement" {
		expectedHash = ManagementHash
		operation = "content.post_collection.GetPostCollectionManagement"
		root = "postCollectionManagement"
		if p.Variables.First == nil || *p.Variables.First != 100 || p.Variables.After != nil {
			fail(w, r, domain.Invalid)
			return
		}
	} else if p.Variables.First == nil || *p.Variables.First < 1 || *p.Variables.First > 100 {
		fail(w, r, domain.Invalid)
		return
	}
	if p.Extensions.PersistedQuery.Version != 1 || p.Extensions.PersistedQuery.Hash != expectedHash {
		fail(w, r, domain.Invalid)
		return
	}
	caller, ok := auth.PrincipalFromContext(r.Context())
	if !ok || caller.Subject != "service:api-edge" || caller.Actor.PersonaID != "" || !contains(caller.Roles, "service") || !contains(strings.Fields(caller.Scope), Scope) {
		fail(w, r, domain.Unauthorized)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 1500*time.Millisecond)
	defer cancel()
	viewer := ""
	grant := r.Header.Get("X-Collection-Query-Grant")
	if grant != "" {
		if h.Authority == nil {
			fail(w, r, domain.StorageRead)
			return
		}
		binding := auth.CollectionQueryBinding{OperationID: operation, CollectionID: p.Variables.CollectionID, PersistedHash: expectedHash, BodyDigest: auth.DelegatedRequestDigest(raw), Method: r.Method, Path: r.URL.Path, Surface: r.Header.Get("X-Client-Surface"), RequestID: r.Header.Get("X-Request-ID")}
		identity, e := h.Authority.Verify(ctx, grant, binding)
		if e != nil {
			fail(w, r, domain.Unauthorized)
			return
		}
		viewer = identity.PersonaID
	} else if root == "postCollectionManagement" {
		fail(w, r, domain.Unauthorized)
		return
	}
	if h.Service == nil {
		fail(w, r, domain.StorageRead)
		return
	}
	var result any
	if root == "postCollectionManagement" {
		view, e := h.Service.GetManagement(ctx, viewer, p.Variables.CollectionID)
		if e != nil {
			fail(w, r, e)
			return
		}
		if len(view.Members) > 100 {
			fail(w, r, domain.Invalid)
			return
		}
		result = view
	} else {
		after := ""
		if p.Variables.After != nil {
			after = *p.Variables.After
		}
		view, e := h.Service.Get(ctx, viewer, p.Variables.CollectionID, after, *p.Variables.First)
		if e != nil {
			fail(w, r, e)
			return
		}
		result = view
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Contract-Graph-SHA256", h.GraphHash)
	_ = json.NewEncoder(w).Encode(map[string]any{"data": map[string]any{root: result}})
}
func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
func fail(w http.ResponseWriter, r *http.Request, err error) {
	var out error
	switch {
	case errors.Is(err, domain.Unauthorized):
		out = generated.AppErrorFromPostCollectionUnauthorized("")
	case errors.Is(err, domain.Invalid):
		out = generated.AppErrorFromPostCollectionInvalidArgument("")
	case errors.Is(err, domain.Unavailable):
		out = generated.AppErrorFromPostCollectionUnavailable("")
	case errors.Is(err, domain.Conflict):
		out = generated.AppErrorFromPostCollectionVersionConflict("")
	default:
		out = generated.AppErrorFromPostCollectionReadFailed("")
	}
	rterr.WriteHTTPError(w, out, rterr.HTTPWriteOptionsFromRequest(r))
}
