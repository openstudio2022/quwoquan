package local_contract

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	auth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	owner "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
	"strings"
	"testing"
	"time"
)

type collectionIssuer struct {
	calls   int
	failure bool
	binding auth.CollectionQueryBinding
	source  string
}

func (i *collectionIssuer) Issue(_ context.Context, source string, binding auth.CollectionQueryBinding) (auth.CollectionQueryGrantResult, error) {
	i.calls++
	i.binding = binding
	i.source = source
	if i.failure {
		return auth.CollectionQueryGrantResult{}, errors.New("authority down")
	}
	return auth.CollectionQueryGrantResult{Grant: "opaque", ExpiresUnixSeconds: time.Now().Add(time.Minute).Unix()}, nil
}
func TestCollectionExecutorDoesNotDowngradeAuthenticatedFailure(t *testing.T) {
	calls := 0
	var requestBytes []byte
	var grant string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		requestBytes, _ = io.ReadAll(r.Body)
		grant = r.Header.Get("X-Collection-Query-Grant")
		if strings.Contains(string(requestBytes), "source-token") {
			t.Error("source token leaked to owner")
		}
		w.Header().Set("X-Contract-Graph-SHA256", "graph")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":{"postCollection":{"collectionId":"c","ownerPersonaId":"p","name":"n","coverAssetId":null,"visibility":"public","version":1,"members":[],"visibleCount":0,"nextCursor":null,"canManage":false}}}`))
	}))
	defer srv.Close()
	origin, _ := url.Parse(srv.URL)
	issuer := &collectionIssuer{}
	executor := &owner.PostCollectionQueryExecutor{Origin: origin, Client: srv.Client(), Credentials: staticServiceCredentials{header: "Bearer service"}, Authority: issuer, SourceCredential: func(context.Context) (string, error) { return "source-token", nil }, GraphHash: "graph"}
	entry := domain.Entry{OperationName: "PostCollection", CanonicalOperationID: "content.post_collection.GetPostCollection", SHA256Hash: "aabadb9772a276ea6c2837d0b04508e7fcbb1d8be5d6194e01ba837a6dee0f5a", OperationType: "query", ObjectIDs: []string{"content.post_collection"}, ExecutorKey: owner.CollectionExecutorKey}
	variables := map[string]any{"collectionId": "c", "first": json.Number("20")}
	if _, err := executor.Execute(context.Background(), entry, variables); err != nil || issuer.calls != 0 || grant != "" {
		t.Fatal("anonymous", err)
	}
	ctx := auth.WithPrincipal(context.Background(), auth.Principal{Actor: operation.ActorContext{AccountID: "a", PersonaID: "p"}})
	if _, err := executor.Execute(ctx, entry, variables); err != nil || issuer.source != "source-token" || grant != "opaque" || issuer.binding.BodyDigest != auth.DelegatedRequestDigest(requestBytes) {
		t.Fatal("authenticated", err)
	}
	before := calls
	issuer.failure = true
	if _, err := executor.Execute(ctx, entry, variables); err == nil || calls != before {
		t.Fatal("authority failure downgraded")
	}
	invalid := entry
	invalid.SHA256Hash = "wrong"
	if _, err := executor.Execute(ctx, invalid, variables); err == nil || calls != before {
		t.Fatal("unknown hash reached owner")
	}
	accountOnly := auth.WithPrincipal(context.Background(), auth.Principal{Actor: operation.ActorContext{AccountID: "a"}})
	if _, err := executor.Execute(accountOnly, entry, variables); err == nil {
		t.Fatal("incomplete identity downgraded")
	}
}
