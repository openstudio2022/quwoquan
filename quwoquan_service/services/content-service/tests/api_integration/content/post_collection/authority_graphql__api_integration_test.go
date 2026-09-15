//go:build api_integration

package collection_test

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t2
import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/internal/platform/testinfra"
	auth "quwoquan_service/runtime/auth"
	graphql "quwoquan_service/services/content-service/internal/content/post_collection/adapters/inbound/graphql"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	persistence "quwoquan_service/services/content-service/internal/content/post_collection/infrastructure/persistence"
	"strings"
	"testing"
	"time"
)

type verifyingAuthority struct {
	grant, bindingDigest string
	allow                bool
}

func (a *verifyingAuthority) Verify(_ context.Context, grant string, b auth.CollectionQueryBinding) (auth.VerifiedCollectionQueryIdentity, error) {
	if !a.allow || grant != a.grant || b.BodyDigest != a.bindingDigest || b.PersistedHash != graphql.ManagementHash || b.Method != "POST" || b.Path != "/internal/graphql" || b.Surface != "postCollection" {
		return auth.VerifiedCollectionQueryIdentity{}, fmt.Errorf("authority denied")
	}
	return auth.VerifiedCollectionQueryIdentity{AccountID: "account", PersonaID: "owner", AuthEpoch: 1, ExpiresUnixSeconds: time.Now().Add(time.Minute).Unix()}, nil
}
func TestCollectionPersistedHTTPMongo(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	container, e := mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	if e != nil {
		t.Fatal(e)
	}
	defer container.Terminate(context.Background())
	uri, e := container.ConnectionString(ctx)
	if e != nil {
		t.Fatal(e)
	}
	client, e := mongo.Connect(options.Client().ApplyURI(uri).SetDirect(true))
	if e != nil {
		t.Fatal(e)
	}
	defer client.Disconnect(context.Background())
	db := client.Database(fmt.Sprintf("collection_persisted_%d", time.Now().UnixNano()))
	defer db.Drop(context.Background())
	store, e := persistence.New(db)
	if e != nil {
		t.Fatal(e)
	}
	posts := &httpPosts{}
	posts.visible.Store(true)
	svc, e := app.New(store, posts, httpCovers{}, time.Now)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = svc.Save(ctx, "owner", domain.Save{ID: "c", Name: "合集", Visibility: domain.Public, PostIDs: []string{"p1", "p2"}}); e != nil {
		t.Fatal(e)
	}
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	cfg := auth.TokenConfig{Secret: secret, Issuer: "test", Audience: "test", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	signer, _ := auth.NewHS256Signer(cfg)
	verifier, _ := auth.NewHS256Verifier(cfg)
	token, _ := signer.Sign(auth.TokenSubject{AccountID: "service:api-edge", Roles: []string{"service"}, Scopes: []string{graphql.Scope}})
	graph := strings.Repeat("a", 64)
	authority := &verifyingAuthority{grant: "opaque-authority-token", allow: true}
	handler := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(graphql.Handler{Service: svc, Authority: authority, GraphHash: graph})
	server := httptest.NewServer(handler)
	defer server.Close()
	invoke := func(name, hash, grant string, vars any) (int, []byte) {
		body, _ := json.Marshal(map[string]any{"operationName": name, "variables": vars, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": hash}}})
		authority.bindingDigest = auth.DelegatedRequestDigest(body)
		r, _ := http.NewRequest("POST", server.URL+"/internal/graphql", bytes.NewReader(body))
		r.Header.Set("Authorization", "Bearer "+token)
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Contract-Graph-SHA256", graph)
		r.Header.Set("X-Collection-Query-Grant", grant)
		r.Header.Set("X-Client-Surface", "postCollection")
		r.Header.Set("X-Request-ID", "request")
		res, e := server.Client().Do(r)
		if e != nil {
			t.Fatal(e)
		}
		defer res.Body.Close()
		var raw json.RawMessage
		if json.NewDecoder(res.Body).Decode(&raw) != nil {
			t.Fatal("response invalid")
		}
		return res.StatusCode, raw
	}
	if status, _ := invoke("PostCollection", graphql.ReadHash, "", map[string]any{"collectionId": "c", "first": 1}); status != 200 {
		t.Fatal(status)
	}
	if status, _ := invoke("PostCollectionManagement", graphql.ManagementHash, "", map[string]any{"collectionId": "c", "first":100}); status != 401 {
		t.Fatal(status)
	}
	if status, _ := invoke("PostCollectionManagement", graphql.ManagementHash, authority.grant, map[string]any{"collectionId": "c", "first":100}); status != 200 {
		t.Fatal(status)
	}
	posts.visible.Store(false)
	if status, raw := invoke("PostCollection", graphql.ReadHash, "", map[string]any{"collectionId": "c", "first": 1}); status != 200 || !bytes.Contains(raw, []byte(`"visibleCount":0`)) {
		t.Fatal(status, string(raw))
	}
	if status, raw := invoke("PostCollectionManagement", graphql.ManagementHash, authority.grant, map[string]any{"collectionId": "c", "first":100}); status != 200 || bytes.Contains(raw, []byte(`"title":"`)) {
		t.Fatal("restricted member leak", status, string(raw))
	}
	authority.allow = false
	if status, _ := invoke("PostCollectionManagement", graphql.ManagementHash, authority.grant, map[string]any{"collectionId": "c", "first":100}); status == 200 {
		t.Fatal("revoked admitted")
	}
	for _, name := range []string{"PostCollection", "Unknown", "mutation"} {
		if status, _ := invoke(name, strings.Repeat("f", 64), "", map[string]any{"collectionId": "c", "first": 1}); status == 200 {
			t.Fatal("unknown hash/name admitted")
		}
	}
}
