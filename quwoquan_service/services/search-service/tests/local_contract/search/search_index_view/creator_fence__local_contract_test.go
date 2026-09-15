package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t8
type fenceReader struct {
	value app.ContentCreatorFence
	calls int
}

func (f *fenceReader) Read(context.Context) (app.ContentCreatorFence, error) {
	f.calls++
	return f.value, nil
}
func TestCreatorCursorRejectsContentRevisionChange(t *testing.T) {
	backend := &ownerQueryBackendSpy{docs: []rt.Document{{ObjectType: "user.profile", ObjectID: "a", Title: "作者", Visibility: "public"}, {ObjectType: "user.profile", ObjectID: "b", Title: "作者", Visibility: "public"}}}
	service := newOwnerSearchService(t, backend)
	digest := "sha256:" + strings.Repeat("a", 64)
	input := app.QueryInput{Query: "作者", Mode: "result", ObjectTypes: []string{"user.profile"}, Limit: 1}
	caller := apiEdgeOwnerCaller("session:test|service:api-edge")
	identity := app.QueryExecutionIdentity{CandidateDigest: digest, PolicyDigest: digest, ContentFenceDigest: "revision-a"}
	first, err := service.Execute(t.Context(), input, rt.Viewer{}, caller, identity)
	if err != nil || first.NextCursor == "" {
		t.Fatal("cursor not issued", err)
	}
	input.Cursor = first.NextCursor
	identity.ContentFenceDigest = "revision-b"
	if _, err = service.Execute(t.Context(), input, rt.Viewer{}, caller, identity); !errors.Is(err, app.ErrSearchCursor) {
		t.Fatal("old revision cursor accepted", err)
	}
}

func TestCreatorFencePinsOnceAndRollbackChangesCursorBinding(t *testing.T) {
	now := time.Now().UTC()
	digest := "sha256:" + strings.Repeat("a", 64)
	reader := &fenceReader{value: app.ContentCreatorFence{Found: true, Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "a", ManifestDigest: digest, Revision: 1, ProjectionVersion: 1, ActivatedAt: &now}}
	fence, err := app.NewCreatorQueryFence(reader, "gamma", digest,digest)
	if err != nil {
		t.Fatal(err)
	}
	_, first, err := fence.Pin(t.Context())
	if err != nil || reader.calls != 1 {
		t.Fatal(first, err, reader.calls)
	}
	reader.value.ReleaseID = "b"
	reader.value.Revision = 2
	_, second, err := fence.Pin(t.Context())
	if err != nil || second == first {
		t.Fatal("candidate switch not bound", err)
	}
	reader.value.ReleaseID = "a"
	reader.value.Revision = 3
	_, rollback, err := fence.Pin(t.Context())
	if err != nil || rollback == first {
		t.Fatal("rollback reuses cursor generation", err)
	}
	reader.value.Found = false
	if _, _, err = fence.Pin(t.Context()); err == nil {
		t.Fatal("malformed absent accepted")
	}
	raw, _ := json.Marshal(app.QueryExecutionIdentity{CandidateDigest: digest, PolicyDigest: digest, ContentFenceDigest: rollback})
	if !strings.Contains(string(raw), rollback) {
		t.Fatal("cursor identity lost fence")
	}
}
