package preparation_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"quwoquan_service/generated/operationsecurity"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	msg "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	fence "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/contentfence"
	provider "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/creatorprojection"
	inbound "quwoquan_service/services/search-service/internal/search/search_release_preparation/adapters/inbound/http"
	prepare "quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	persistence "quwoquan_service/services/search-service/internal/search/search_release_preparation/infrastructure/persistence"
	"quwoquan_service/services/search-service/tests/support"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type jointFenceProof struct {
	s      *prepare.Service
	schema string
}

func (p jointFenceProof) VerifyFenceCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (string, error) {
	return p.s.ReconcileRelease(ctx, b, p.schema)
}

type jointAckTransport struct {
	msg.DurableDeliveryTransport
	fail atomic.Bool
}

func (t *jointAckTransport) AckDurable(ctx context.Context, stream, group string, ids ...string) error {
	if t.fail.Swap(false) {
		return fmt.Errorf("injected ACK disconnection")
	}
	return t.DurableDeliveryTransport.AckDurable(ctx, stream, group, ids...)
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestFenceJointSearchHarness(t *testing.T) {
	addr, content := os.Getenv("QWQ_FENCE_JOINT_REDIS"), os.Getenv("QWQ_FENCE_JOINT_CONTENT")
	if addr == "" || content == "" {
		t.Skip("joint runner required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 210*time.Second)
	defer cancel()
	db, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("fence_joint_search"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { c, x := context.WithTimeout(context.Background(), 20*time.Second); defer x(); _ = db.Close(c) }()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	// 先用直接canonical client创建索引，避免测试HTTP故障代理参与Provider启动。
	directClient, e := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "joint_fence", RequestTimeout: 10 * time.Second})
	if e != nil {
		t.Fatal(e)
	}
	if e = directClient.EnsureIndex(ctx); e != nil {
		t.Fatal("direct ES startup", e)
	}
	var esFail atomic.Bool
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if esFail.Load() {
			http.Error(w, "injected provider unavailable", 503)
			return
		}
		request, e := http.NewRequestWithContext(r.Context(), r.Method, endpoint+r.URL.RequestURI(), r.Body)
		if e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		if value := r.Header.Get("Content-Type"); value != "" {
			request.Header.Set("Content-Type", value)
		}
		response, e := http.DefaultClient.Do(request)
		if e != nil {
			http.Error(w, e.Error(), 503)
			return
		}
		defer response.Body.Close()
		for k, v := range response.Header {
			w.Header()[k] = v
		}
		w.WriteHeader(response.StatusCode)
		_, _ = io.Copy(w, response.Body)
	}))
	defer proxy.Close()
	client, err := es.NewClient(es.Config{Endpoints: []string{proxy.URL}, Index: "joint_fence", RequestTimeout: 10 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoStore(db.Database)
	if err = store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	generation := "sha256:" + strings.Repeat("a", 64)
	service, err := prepare.NewService(store, app.NewReleaseCandidateProjector(provider.NewProvider(client, client, "joint_fence-v1")), "alpha", generation, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	api := http.NewServeMux()
	inbound.NewHandler(service).Register(api)
	tokenConfig := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x64}, 32), Issuer: "joint-fence", Audience: "content-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, err := auth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	protected := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("search"))(api))
	prepareServer := httptest.NewServer(protected)
	defer prepareServer.Close()
	signer, err := auth.NewHS256ServiceAuthorizationProvider(tokenConfig, "content-service", []string{"search.release.prepare"})
	if err != nil {
		t.Fatal(err)
	}
	// 三kind公开源为typed fixture；实际HTTP prepare/checkpoint/ES/query proof均为生产实现。
	for _, name := range []string{"a", "b"} {
		release := rt.ReleaseCandidateBinding{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "joint-" + name, ManifestDigest: "sha256:" + strings.Repeat(name, 64)}
		identity := rt.ReleaseCandidateObjectIdentity{Release: release, ObjectType: "content.post", ObjectID: "post-" + name, SourceVersion: 1, SourceDigest: generation}
		posts := rt.ReleasePostCandidateSnapshot{Release: release, SourceClosureDigest: generation, MediaClosureDigest: generation, Posts: []rt.ReleasePostPublicSnapshot{{Identity: identity, PostRef: "posts/" + name, AuthorID: "author", AuthorDisplayName: "作者", ContentType: "article", ContentIdentity: "work", Status: "published", Visibility: "public", ModerationStatus: "approved", Title: "联合搜索" + name, TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{}, MediaURLs: []string{}, PublishedAt: "2026-09-13T00:00:00Z", UpdatedAt: "2026-09-13T00:00:00Z", DeepLink: "quwoquan://content/posts/post-" + name}}}
		if err = posts.Seal(); err != nil {
			t.Fatal(err)
		}
		identity.ObjectType = "entity.homepage"
		identity.ObjectID = "home-" + name
		homes := rt.ReleaseHomepageCandidateSnapshot{Release: release, SourceClosureDigest: generation, EntityRefMappingDigest: generation, Homepages: []rt.ReleaseHomepagePublicSnapshot{{Identity: identity, EntityRef: "entity/" + name, CanonicalEntityID: "entity-" + name, Title: "联合主页" + name, HomepageType: "sight", TagRefs: []string{}, UpdatedAt: "2026-09-13T00:00:00Z", DeepLink: "quwoquan://homepages/home-" + name}}}
		if err = homes.Seal(); err != nil {
			t.Fatal(err)
		}
		creators := rt.CreatorSearchCandidateSnapshot{Release: release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{{ObjectType: "user.profile", ObjectID: "creator-" + name, PersonaID: "creator-" + name, CreatorID: "creator-" + name, AuthorID: "author-" + name, UserHandle: "handle-" + name, DisplayName: "联合作者" + name, IdentityTags: []string{}, SourceVersion: 1, ProfileDigest: generation, UpdatedAt: "2026-09-13T00:00:00Z"}}}
		if err = creators.Seal(); err != nil {
			t.Fatal(err)
		}
		for _, snapshot := range []rt.SearchReleaseCandidateSnapshot{{Kind: "creator", Creator: &creators}, {Kind: "post", Post: &posts}, {Kind: "homepage", Homepage: &homes}} {
			binding := rt.ReleaseQueryPreparationBinding{Release: release, Slice: snapshot.Kind + "_search", ProviderBindingGeneration: generation, SchemaGeneration: client.SchemaGeneration()}
			version := int64(0)
			for attempt := 0; attempt < 12; attempt++ {
				command := domain.Command{Binding: binding, Snapshot: snapshot, ExpectedVersion: version, IdempotencyKey: name + snapshot.Kind + strconv.Itoa(attempt)}
				raw, _ := json.Marshal(command)
				request, _ := http.NewRequestWithContext(ctx, http.MethodPost, prepareServer.URL+"/internal/search/release-preparations:prepare", bytes.NewReader(raw))
				header, e := signer.AuthorizationHeader(ctx)
				if e != nil {
					t.Fatal(e)
				}
				request.Header.Set("Authorization", header)
				request.Header.Set("Idempotency-Key", command.IdempotencyKey)
				response, e := http.DefaultClient.Do(request)
				if e != nil {
					t.Fatal(e)
				}
				var view domain.View
				e = json.NewDecoder(response.Body).Decode(&view)
				response.Body.Close()
				if response.StatusCode != 200 || e != nil {
					t.Fatal("prepare", response.StatusCode, e, view)
				}
				if view.Status == "completed" {
					break
				}
				if attempt == 11 {
					t.Fatal("prepare incomplete", view)
				}
				version = view.Version
				time.Sleep(100 * time.Millisecond)
			}
		}
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{Scenes: map[string]rtredis.SceneConfig{"general": {Mode: "standalone", Addr: addr}}, DefaultScene: "general"})
	defer router.Close()
	baseTransport, err := msg.NewRedisMessageTransport(router.Scene("general"), router.Scene("general"))
	if err != nil {
		t.Fatal(err)
	}
	transport := &jointAckTransport{DurableDeliveryTransport: baseTransport}
	credential, err := auth.NewHS256ServiceAuthorizationProvider(tokenConfig, "search-service", []string{"content.release.fence.read"})
	if err != nil {
		t.Fatal(err)
	}
	current, err := fence.NewReader(content, "alpha", credential)
	if err != nil {
		t.Fatal(err)
	}
	commits, err := fence.NewCommitReader(content, credential)
	if err != nil {
		t.Fatal(err)
	}
	receipts := fence.NewReconciliationStore(db.Database)
	if err = receipts.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	reconciler, err := app.NewContentFenceReconciler(receipts, commits, current, jointFenceProof{service, client.SchemaGeneration()}, "alpha")
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := app.NewContentPostLifecycleConsumer(transport, reconciler, "joint-search-fence", "search-one")
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{}, 1)
	controls := http.NewServeMux()
	controls.HandleFunc("/process", func(w http.ResponseWriter, r *http.Request) {
		n, e := consumer.ProcessOnce(ctx)
		result := map[string]any{"processed": n, "healthy": consumer.Healthy(time.Minute) == nil}
		if e != nil {
			result["error"] = e.Error()
		}
		count, _ := db.Database.Collection("search_content_fence_receipts").CountDocuments(ctx, bson.M{})
		result["receipts"] = count
		_ = json.NewEncoder(w).Encode(result)
	})
	controls.HandleFunc("/ack-fail", func(w http.ResponseWriter, r *http.Request) { transport.fail.Store(true); w.WriteHeader(204) })
	controls.HandleFunc("/provider-fail", func(w http.ResponseWriter, r *http.Request) {
		esFail.Store(r.URL.Query().Get("fail") == "1")
		w.WriteHeader(204)
	})
	controls.HandleFunc("/reset", func(w http.ResponseWriter, r *http.Request) {
		_, _ = db.Database.Collection("search_content_fence_receipts").DeleteMany(ctx, bson.M{})
		w.WriteHeader(204)
	})
	controls.HandleFunc("/done", func(w http.ResponseWriter, r *http.Request) {
		select {
		case done <- struct{}{}:
		default:
		}
		w.WriteHeader(204)
	})
	server := httptest.NewServer(controls)
	defer server.Close()
	fmt.Printf("SEARCH_FENCE_JOINT_READY %s\n", server.URL)
	select {
	case <-done:
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
}
