//go:build api_integration

package collection_test

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-001.t2
import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	inbound "quwoquan_service/services/content-service/internal/content/post_collection/adapters/inbound/http"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	persistence "quwoquan_service/services/content-service/internal/content/post_collection/infrastructure/persistence"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// 上游状态由对象公开 reader seam 提供；测试不直写 Post 存储。
type httpPosts struct{ visible atomic.Bool }

func (p *httpPosts) ReadVisible(_ context.Context, id, viewer string) (app.Member, bool, error) {
	return app.Member{PostID: id, ContentType: "video", Title: "视频"}, p.visible.Load(), nil
}

type httpCovers struct{}

func (httpCovers) CanUseCover(context.Context, string, string, domain.Visibility) (bool, error) {
	return false, nil
}
func exerciseHTTP(t *testing.T, db *mongo.Database) {
	t.Helper()
	store, _ := persistence.New(db)
	posts := &httpPosts{}
	posts.visible.Store(true)
	start := func() *httptest.Server {
		service, e := app.New(store, posts, httpCovers{}, time.Now)
		if e != nil {
			t.Fatal(e)
		}
		mux := http.NewServeMux()
		inbound.Handler{Service: service}.Register(mux)
		return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("X-Test-Actor") == "owner" {
				r = r.WithContext(rtauth.WithPrincipal(r.Context(), rtauth.Principal{Actor: operation.ActorContext{AccountID: "account", PersonaID: "owner"}}))
			}
			mux.ServeHTTP(w, r)
		}))
	}
	server := start()
	send := func(method, actor string, body any) (int, []byte) {
		raw, e := json.Marshal(body)
		if e != nil {
			t.Fatal(e)
		}
		req, e := http.NewRequest(method, server.URL+"/content/collections/http?limit=1", bytes.NewReader(raw))
		if e != nil {
			t.Fatal(e)
		}
		req.Header.Set("X-Test-Actor", actor)
		res, e := server.Client().Do(req)
		if e != nil {
			t.Fatal(e)
		}
		defer res.Body.Close()
		data, _ := io.ReadAll(res.Body)
		return res.StatusCode, data
	}
	command := struct {
		ExpectedVersion int64    `json:"expectedVersion"`
		Name            string   `json:"name"`
		Visibility      string   `json:"visibility"`
		PostIDs         []string `json:"postIds"`
	}{0, "HTTP合集", "public", []string{"p"}}
	if status, body := send(http.MethodPut, "", command); status != 401 {
		t.Fatalf("anonymous write %d %s", status, body)
	}
	if status, body := send(http.MethodPut, "owner", command); status != 200 {
		t.Fatalf("create %d %s", status, body)
	}
	server.Close()
	server = start()
	defer server.Close()
	status, body := send(http.MethodGet, "", nil)
    if status != http.StatusMethodNotAllowed { t.Fatalf("retired REST query remains registered: %d", status) }
	if status, body = send(http.MethodDelete, "owner", struct {
		ExpectedVersion int64 `json:"expectedVersion"`
	}{1}); status != 200 {
		t.Fatalf("delete %d %s", status, body)
	}
	if status, _ = send(http.MethodGet, "", nil); status != http.StatusMethodNotAllowed {
		t.Fatalf("deleted query %d", status)
	}
}

func TestMongoCASAndReopenConformance(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	uri := os.Getenv("TEST_MONGO_URI")
	if uri == "" {
		testinfra.ConfigureLocalContainerRuntime()
		container, e := mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
		if e != nil {
			t.Fatalf("GATE_BLOCK: real Mongo conformance provider: %v", e)
		}
		defer container.Terminate(context.Background())
		uri, e = container.ConnectionString(ctx)
		if e != nil {
			t.Fatal(e)
		}
	}
	client, err := mongo.Connect(options.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Disconnect(context.Background())
	if err = client.Ping(ctx, nil); err != nil {
		t.Fatal(err)
	}
	db := client.Database(fmt.Sprintf("collection_conformance_%d", time.Now().UnixNano()))
	defer db.Drop(context.Background())
	store, err := persistence.New(db)
	if err != nil {
		t.Fatal(err)
	}
	exerciseHTTP(t, db)
	c := domain.Collection{ID: "c", Owner: "owner", Name: "真实合集", Visibility: domain.Public, PostIDs: []string{"video", "image", "article"}, Version: 1, Status: domain.Active, UpdatedAt: time.Unix(1000, 0)}
	ok, err := store.CompareAndSwap(ctx, c, 0)
	if err != nil || !ok {
		t.Fatalf("create %v %v", ok, err)
	}
	other, err := mongo.Connect(options.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatal(err)
	}
	defer other.Disconnect(context.Background())
	reopened, _ := persistence.New(other.Database(db.Name()))
	got, found, err := reopened.Find(ctx, "c")
	if err != nil || !found || got.Name != c.Name || len(got.PostIDs) != 3 {
		t.Fatalf("reopen %+v %v %v", got, found, err)
	}
	c.Version = 2
	var wins atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ok, e := reopened.CompareAndSwap(ctx, c, 1)
			if e != nil {
				t.Error(e)
			}
			if ok {
				wins.Add(1)
			}
		}()
	}
	wg.Wait()
	if wins.Load() != 1 {
		t.Fatalf("CAS winners %d", wins.Load())
	}
	c.Owner = "intruder"
	c.Version = 3
	if ok, e := store.CompareAndSwap(ctx, c, 2); e != nil || ok {
		t.Fatalf("owner CAS %v %v", ok, e)
	}
	c.Owner = "owner"
	c.Status = domain.Deleted
	if ok, e := store.CompareAndSwap(ctx, c, 2); e != nil || !ok {
		t.Fatalf("delete %v %v", ok, e)
	}
	got, found, err = reopened.Find(ctx, "c")
	if err != nil || !found || got.Status != domain.Deleted || got.Version != 3 {
		t.Fatalf("tombstone %+v %v", got, err)
	}
	c.Status = domain.Active
	c.Version = 4
	if ok, e := store.CompareAndSwap(ctx, c, 3); e != nil || ok {
		t.Fatalf("resurrection %v %v", ok, e)
	}
}
