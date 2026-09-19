package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/premium_pool_entry/contract/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/contentsource"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/persistence"
	"testing"
	"time"
	"github.com/jackc/pgx/v5/pgxpool"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestProductionEnsureSchemaDiscoversMigrationAndBlocksNonemptyHistory(t *testing.T) {
 ctx:=context.Background()
 for _,nonempty:=range []bool{false,true} {
  schema:=fmt.Sprintf("premium_migration_%d",time.Now().UnixNano())
  if _,err:=premiumPoolPGPool.Exec(ctx,"CREATE SCHEMA "+schema);err!=nil{t.Fatal(err)}
  cfg:=premiumPoolPGPool.Config().Copy();cfg.ConnConfig.RuntimeParams["search_path"]=schema
  pool,err:=pgxpool.NewWithConfig(ctx,cfg);if err!=nil{t.Fatal(err)}
  store,_:=persistence.NewPostgresStore(pool);if err:=store.EnsureSchema(ctx);err!=nil{t.Fatal(err)}
  if nonempty {service:=application.NewService(store);_,err:=service.Upsert(ctx,application.UpsertCommand{ContentID:"ordinary",Scope:"global",QualityScore:.9,QualityAdmission:"approved",AuditID:"audit",ExpiresAt:time.Now().Add(time.Hour),Context:ports.CommandContext{ActorID:"op",Environment:"gamma",RequestID:"r",TraceID:"t",IdempotencyKey:"migration"}});if err!=nil{t.Fatal(err)}}
  if _,err:=pool.Exec(ctx,"ALTER TABLE premium_pool_entries DROP COLUMN release_admissions");err!=nil{t.Fatal(err)}
  err=store.EnsureSchema(ctx)
  if nonempty && err==nil {t.Fatal("nonempty history silently backfilled")};if !nonempty && err!=nil {t.Fatal(err)}
  pool.Close()
 }
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
// Content HTTP服务为typed source替身，PG为独立真实实例，不是Content联合CAS证据。
func TestReleaseAdmissionsSourceHTTPAndAtomicPostgresOutbox(t *testing.T) {
	ctx := context.Background()
	store, _ := persistence.NewPostgresStore(premiumPoolPGPool)
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	d := "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	release := rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "release-A", ManifestDigest: d}
	id := fmt.Sprintf("release-post-%d", time.Now().UnixNano())
	now := time.Now().UTC().Truncate(time.Second)
	snapshot := rt.ReleasePostCandidateSnapshot{Release: release, SourceClosureDigest: d, MediaClosureDigest: d, Posts: []rt.ReleasePostPublicSnapshot{{Identity: rt.ReleaseCandidateObjectIdentity{Release: release, ObjectType: "content.post", ObjectID: id, SourceVersion: 1, SourceDigest: d}, PostRef: "ref", AuthorID: "author", AuthorDisplayName: "Author", ContentType: "video", Status: "published", Visibility: "public", ModerationStatus: "approved", TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{}, MediaURLs: []string{}, PublishedAt: now.Format(time.RFC3339), UpdatedAt: now.Format(time.RFC3339), DeepLink: "/post/" + id}}}
	if err := snapshot.Seal(); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/internal/content/release-candidates:query" || r.Header.Get("Authorization") != "Bearer source-test" {
			http.Error(w, "forbidden", 403)
			return
		}
		_ = json.NewEncoder(w).Encode(snapshot)
	}))
	defer server.Close()
	reader := &contentsource.Reader{Endpoint: server.URL, Client: server.Client(), Credential: func(context.Context) (string, error) { return "source-test", nil }}
	service := application.NewService(store).WithCandidateSource(reader)
	encoded, _ := json.Marshal(snapshot.Posts[0].Identity)
	var identity generated.ReleaseCandidateObjectIdentity
	_ = json.Unmarshal(encoded, &identity)
	command := application.UpsertCommand{ContentID: id, Scope: "global", QualityScore: .9, QualityAdmission: "approved", AuditID: "audit", SupplySource: "qwq_data", ExpiresAt: now.Add(time.Hour), ReleaseSource: &identity, Context: ports.CommandContext{ActorID: "operator-a", Environment: "gamma", RequestID: "request", TraceID: "trace", IdempotencyKey: id}}
	created, err := service.Upsert(ctx, command)
	if err != nil {
		t.Fatal(err)
	}
	if len(created.ReleaseAdmissions) != 1 {
		t.Fatal("missing member")
	}
	loaded, _, err := store.Load(ctx, id)
	if err != nil || len(loaded.ReleaseAdmissions) != 1 {
		t.Fatal("PG member missing", err)
	}
	var count int
	if err := premiumPoolPGPool.QueryRow(ctx, "SELECT count(*) FROM premium_pool_entry_outbox WHERE aggregate_id=$1 AND jsonb_array_length(payload->'releaseAdmissions')=1", id).Scan(&count); err != nil || count != 1 {
		t.Fatal("outbox member missing", err, count)
	}
	command.Context.IdempotencyKey = id + "-wrong"
	identity.SourceVersion = 2
	if _, err := service.Upsert(ctx, command); err == nil {
		t.Fatal("source version mismatch accepted")
	}
	identity.SourceVersion = 1
	rollback := command.Context
	rollback.IdempotencyKey = id + "-rollback"
	revoked, err := service.Rollback(ctx, id, rollback)
	if err != nil || revoked.ReleaseAdmissions[0].Status != "rolled_back" {
		t.Fatal("member revocation failed", err)
	}
}
