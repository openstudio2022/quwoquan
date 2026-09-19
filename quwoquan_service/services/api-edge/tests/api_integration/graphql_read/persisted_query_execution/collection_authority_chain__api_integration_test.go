package api_integration

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t2
import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http/httptest"
	"net/url"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	auth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	edge "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
	content "quwoquan_service/services/content-service/cmd/api"
	user "quwoquan_service/services/user-service/cmd/api"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type chainAccounts struct{ epoch atomic.Int64 }

func (a *chainAccounts) ReadAccountSecurity(context.Context, string) (user.CollectionQuerySecuritySnapshot, error) {
	return user.CollectionQuerySecuritySnapshot{AccountState: "active", AuthEpoch: a.epoch.Load()}, nil
}

type chainPersonas struct{ active atomic.Bool }

func (p *chainPersonas) ResolveOwnerAccountID(context.Context, string) (string, bool, error) {
	return "account", p.active.Load(), nil
}

type chainPosts struct{ visible atomic.Bool }

func (p *chainPosts) ReadVisible(_ context.Context, id, viewer string) (content.CollectionMember, bool, error) {
	return content.CollectionMember{PostID: id, Title: "作品", ContentType: "video"}, p.visible.Load(), nil
}

type chainCovers struct{}

func (chainCovers) CanUseCover(context.Context, string, string, content.CollectionVisibility) (bool, error) {
	return false, nil
}

type chainCredential struct {
	signer         *auth.Signer
	service, scope string
}

func (c chainCredential) AuthorizationHeader(context.Context) (string, error) {
	token, e := c.signer.Sign(auth.TokenSubject{AccountID: "service:" + c.service, Roles: []string{"service"}, Scopes: []string{c.scope}})
	return "Bearer " + token, e
}
func TestCollectionAuthorityEdgeOwnerHTTPMongoChain(t *testing.T) {
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
	mongoClient, e := mongo.Connect(options.Client().ApplyURI(uri).SetDirect(true))
	if e != nil {
		t.Fatal(e)
	}
	defer mongoClient.Disconnect(context.Background())
	db := mongoClient.Database(fmt.Sprintf("collection_chain_%d", time.Now().UnixNano()))
	defer db.Drop(context.Background())
	secret := make([]byte, 32)
	_, _ = rand.Read(secret)
	config := auth.TokenConfig{Secret: secret, Issuer: "test", Audience: "test", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	signer, _ := auth.NewHS256Signer(config)
	verifier, _ := auth.NewHS256Verifier(config)
	key := make([]byte, 32)
	_, _ = rand.Read(key)
	accounts := &chainAccounts{}
	accounts.epoch.Store(1)
	personas := &chainPersonas{}
	personas.active.Store(true)
	ah, e := user.NewCollectionQueryAuthorityHTTP(verifier, accounts, personas, "ephemeral", map[string][]byte{"ephemeral": key}, time.Now)
	if e != nil {
		t.Fatal(e)
	}
	asrv := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("user"))(ah)))
	defer asrv.Close()
	var issuePath, verifyPath string
	for _, d := range operationsecurity.ForDomain("user") {
		switch d.CanonicalOperationID {
		case "user.user_account.IssueCollectionQueryGrant":
			issuePath = d.PathTemplate
		case "user.user_account.VerifyCollectionQueryGrant":
			verifyPath = d.PathTemplate
		}
	}
	issuer, e := auth.NewCollectionQueryAuthorityClient(asrv.URL, issuePath, verifyPath, chainCredential{signer, "api-edge", "user.collection_query.issue"}, asrv.Client())
	if e != nil {
		t.Fatal(e)
	}
	online, e := auth.NewCollectionQueryAuthorityClient(asrv.URL, issuePath, verifyPath, chainCredential{signer, "content-service", "user.collection_query.verify"}, asrv.Client())
	if e != nil {
		t.Fatal(e)
	}
	posts := &chainPosts{}
	posts.visible.Store(true)
	graph := strings.Repeat("a", 64)
	ch, commands, e := content.NewCollectionQueryHTTP(db, posts, chainCovers{}, online, graph)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = commands.Save(ctx, "persona", content.CollectionSave{ID: "c", Name: "合集", Visibility: "public", PostIDs: []string{"p1", "p2"}}); e != nil {
		t.Fatal(e)
	}
	csrv := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(ch))
	defer csrv.Close()
	origin, _ := url.Parse(csrv.URL)
	token, _ := signer.Sign(auth.TokenSubject{AccountID: "account", PersonaID: "persona", AuthEpoch: 1})
	executor := &edge.PostCollectionQueryExecutor{Origin: origin, Client: csrv.Client(), Credentials: chainCredential{signer, "api-edge", edge.CollectionReadScope}, Authority: issuer, SourceCredential: func(context.Context) (string, error) { return token, nil }, GraphHash: graph}
	read := domain.Entry{OperationName: "PostCollection", SHA256Hash: "aabadb9772a276ea6c2837d0b04508e7fcbb1d8be5d6194e01ba837a6dee0f5a", CanonicalOperationID: "content.post_collection.GetPostCollection", OperationType: "query", ObjectIDs: []string{"content.post_collection"}, ExecutorKey: edge.CollectionExecutorKey}
	manage := read
	manage.OperationName = "PostCollectionManagement"
	manage.SHA256Hash = "a57f5fda7db3268872328cb520504de42bd12fe34e97bff61d804674b112d4db"
	manage.CanonicalOperationID = "content.post_collection.GetPostCollectionManagement"
	vars := map[string]any{"collectionId": "c", "first": json.Number("1")}
	mvars := map[string]any{"collectionId": "c", "first": json.Number("100")}
	if _, e = executor.Execute(ctx, read, vars); e != nil {
		t.Fatal("anonymous", e)
	}
	if _, e = executor.Execute(ctx, manage, mvars); e == nil {
		t.Fatal("anonymous management")
	}
	userctx := auth.WithPrincipal(ctx, auth.Principal{Actor: operation.ActorContext{AccountID: "account", PersonaID: "persona"}})
	if _, e = executor.Execute(userctx, manage, mvars); e != nil {
		t.Fatal("owner", e)
	}
	posts.visible.Store(false)
	out, e := executor.Execute(userctx, read, vars)
	if e != nil || !strings.Contains(string(out.Data), `"visibleCount":0`) {
		t.Fatal("dynamic visibility", e)
	}
	accounts.epoch.Store(2)
	if _, e = executor.Execute(userctx, manage, mvars); e == nil {
		t.Fatal("epoch revocation")
	}
	accounts.epoch.Store(1)
	personas.active.Store(false)
	if _, e = executor.Execute(userctx, manage, mvars); e == nil {
		t.Fatal("persona retired")
	}
	personas.active.Store(true)
	// 另一合法 persona 仍不能读取 owner 管理视图。
	otherToken, _ := signer.Sign(auth.TokenSubject{AccountID: "account", PersonaID: "other", AuthEpoch: 1})
	executor.SourceCredential = func(context.Context) (string, error) { return otherToken, nil }
	otherctx := auth.WithPrincipal(ctx, auth.Principal{Actor: operation.ActorContext{AccountID: "account", PersonaID: "other"}})
	if _, e = executor.Execute(otherctx, manage, mvars); e == nil {
		t.Fatal("non owner management admitted")
	}
	executor.SourceCredential = func(context.Context) (string, error) { return token, nil }
	executor.Credentials = chainCredential{signer, "fake-edge", edge.CollectionReadScope}
	if _, e = executor.Execute(userctx, read, vars); e == nil {
		t.Fatal("actual service caller spoof admitted")
	}
	executor.Credentials = chainCredential{signer, "api-edge", edge.CollectionReadScope}
	unknown := read
	unknown.SHA256Hash = strings.Repeat("f", 64)
	if _, e = executor.Execute(userctx, unknown, vars); e == nil {
		t.Fatal("unknown hash admitted")
	}
	cancelled, stop := context.WithCancel(userctx)
	stop()
	if _, e = executor.Execute(cancelled, read, vars); e == nil {
		t.Fatal("cancelled authority chain admitted")
	}
	executor.SourceCredential = func(context.Context) (string, error) { return "", errors.New("credential unavailable") }
	if _, e = executor.Execute(userctx, read, vars); e == nil {
		t.Fatal("authenticated fallback")
	}
}
