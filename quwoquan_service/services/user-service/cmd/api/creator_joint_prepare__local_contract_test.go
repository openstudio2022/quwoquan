package bootstrap

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/bson"
	"net/http"
	"net/http/httptest"
	"os/exec"
	"path/filepath"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	searchbootstrap "quwoquan_service/services/search-service/cmd/api"
	"quwoquan_service/services/search-service/tests/support"
	accountstore "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	personastore "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	model "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	creatorstore "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t6
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
// 生产User reader/handler + Content/Search公开bootstrap，跨服务仅HTTP；无active前置，不伪造历史CAS。
func TestCreatorJointCandidatePreparationWithoutActive(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 4*time.Minute)
	defer cancel()
	mongoRuntime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("creator_joint_user"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		_ = mongoRuntime.Close(c)
	}()
	pg, err := testinfra.StartPostgresFixture(t.TempDir(), 0)
	if err != nil {
		t.Fatal(err)
	}
	defer pg.Close()
	pool, err := pgxpool.New(ctx, pg.DSN())
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	if err = accountstore.RunManagedMigrations(ctx, pool); err != nil {
		t.Fatal(err)
	}
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	provider, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "creator_joint", RequestTimeout: 30 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = provider.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	// 使用现役canonical绑定算法从配置声明构造隔离测试binding，不取endpoint临时hash。
	moduleRoot, _ := filepath.Abs("../../../..")
	repoRoot := filepath.Dir(moduleRoot)
	script := `import copy,json,yaml; from pathlib import Path; from quwoquan_ops.cli.lib.data_plane_binding import canonical_data_plane_binding
p=yaml.safe_load(Path('quwoquan_ops/environments/gamma/runtime.yaml').read_text()); candidates=[]
def walk(v):
 if isinstance(v,dict):
  if 'dataPlane' in v: candidates.append(v)
  for x in v.values():walk(x)
 elif isinstance(v,list):
  for x in v:walk(x)
walk(p)
t=copy.deepcopy(candidates[0])
for b in t['dataPlane']['bindings'].values():
 if b['slot'].startswith('search.objects.'):b['namespace']='creator_joint-v1'
print(canonical_data_plane_binding(t,target_name='gamma-local')['bindingDigest'])`
	cmd := exec.CommandContext(ctx, "python3", "-B", "-c", script)
	cmd.Dir = repoRoot
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("canonical binding: %s %v", out, err)
	}
	generation := strings.TrimSpace(string(out))
	release := rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "joint-candidate", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}
	store := creatorstore.NewCreatorReleaseCandidateStore(mongoRuntime.Database)
	if err = store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	identity := model.ReleaseIdentity{Environment: release.Environment, SourceOwner: release.SourceOwner, ReleaseID: release.ReleaseID, ManifestDigest: release.ManifestDigest}
	now := time.Date(2026, 9, 12, 0, 0, 0, 0, time.UTC)
	profileDigest := "sha256:" + strings.Repeat("b", 64)
	profile := model.CreatorRuntimeProfile{CreatorID: "joint-creator", PersonaID: "builtin_joint", Handle: "joint-handle", DisplayName: "联合旅行作者", PackageDigest: release.ManifestDigest, ReleaseID: release.ReleaseID, Status: "candidate", ManagedBy: "qwq_data", ImportedAt: now, UpdatedAt: now}
	projection := model.CreatorReleaseProjection{ReleaseIdentity: identity, CreatorID: profile.CreatorID, PersonaID: profile.PersonaID, Profile: profile, AuthorID: profile.PersonaID, ProfileDigest: profileDigest, ProjectionVersion: 1, VerifiedAt: now}
	projection.DocumentDigest, err = creatorstore.DocumentDigest(projection, "documentDigest")
	if err != nil {
		t.Fatal(err)
	}
	state := model.CreatorReleaseCandidateState{ReleaseIdentity: identity, Status: "verified", ProjectionVersion: 1, VerifiedAt: now, ClosureDigest: creatorstore.ClosureDigest([]string{profile.CreatorID + "=" + projection.DocumentDigest}), ExpectedCount: 1, ProjectedCount: 1, AuthorIDs: []string{profile.PersonaID}, ProfileDigests: []model.CreatorProfileDigestBinding{{CreatorID: profile.CreatorID, AuthorID: profile.PersonaID, Digest: profileDigest}}}
	if _, err = store.Stage(ctx, state, []model.CreatorReleaseProjection{projection}); err != nil {
		t.Fatal(err)
	}
	cfg := auth.TokenConfig{Secret: []byte("0123456789abcdef0123456789abcdef"), Issuer: "https://joint.quwoquan.test", Audience: "quwoquan-api", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: 5 * time.Minute}
	verifier, _ := auth.NewHS256Verifier(cfg)
	credential := func(service, scope string) auth.ServiceAuthorizationProvider {
		p, e := auth.NewHS256ServiceAuthorizationProvider(cfg, service, []string{scope})
		if e != nil {
			t.Fatal(e)
		}
		return p
	}
	serve := func(domain string, mux *http.ServeMux) *httptest.Server {
		return httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain(domain))(mux)))
	}
	userMux := http.NewServeMux()
	registerCreatorSearchCandidate(userMux, store, personastore.NewPgPersonaStore(pool), accountstore.NewPgProfileStore(pool), "gamma")
	user := serve("user", userMux)
	defer user.Close()
	contentDB := mongoRuntime.Client.Database(testinfra.UniqueDatabaseName("creator_joint_content"))
	searchDB := mongoRuntime.Client.Database(testinfra.UniqueDatabaseName("creator_joint_search"))
	defer contentDB.Drop(context.Background())
	defer searchDB.Drop(context.Background())
	contentMux := http.NewServeMux()
	content := serve("content", contentMux)
	defer content.Close()
	searchMux := http.NewServeMux()
	_, err = searchbootstrap.RegisterCreatorPreparation(ctx, searchMux, searchDB, provider, provider, "gamma", generation, "creator_joint-v1", content.URL, credential("search-service", "content.release.fence.read"))
	if err != nil {
		t.Fatal(err)
	}
	search := serve("search", searchMux)
	defer search.Close()
	call := func(base, path, scope, actor, key string, input, output any) int {
		raw, _ := json.Marshal(input)
		req, _ := http.NewRequestWithContext(ctx, "POST", base+path, bytes.NewReader(raw))
		if actor != "" {
			h, e := credential(actor, scope).AuthorizationHeader(ctx)
			if e != nil {
				t.Fatal(e)
			}
			req.Header.Set("Authorization", h)
		}
		if key != "" {
			req.Header.Set("Idempotency-Key", key)
		}
		resp, e := http.DefaultClient.Do(req)
		if e != nil {
			t.Fatal(e)
		}
		defer resp.Body.Close()
		if resp.StatusCode == 200 && output != nil {
			if e = rt.DecodeCreatorValue(resp.Body, output); e != nil {
				t.Fatal(e)
			}
		}
		return resp.StatusCode
	}
	var source struct {
		Found    bool                               `json:"found"`
		Snapshot *rt.CreatorSearchCandidateSnapshot `json:"snapshot"`
	}
	query := struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}{release}
	if status := call(user.URL, "/internal/user/creator-search-candidate:query", "user.creator_search.candidate.read", "content-service", "", query, &source); status != 200 || !source.Found || len(source.Snapshot.Profiles) != 1 {
		t.Fatal("real User candidate read", status, source)
	}
	binding := rt.ReleaseQueryPreparationBinding{Release: release, Slice: "creator_search", SchemaGeneration: provider.SchemaGeneration(), ProviderBindingGeneration: generation}
	type command struct {
		Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
		Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
		ExpectedVersion int64                             `json:"expectedVersion"`
		IdempotencyKey  string                            `json:"idempotencyKey"`
	}
	var result struct {
		PreparationID      string                            `json:"preparationId"`
		Binding            rt.ReleaseQueryPreparationBinding `json:"binding"`
		SnapshotDigest     string                            `json:"snapshotDigest"`
		PreparationVersion int64                             `json:"version"`
		Status             string                            `json:"status"`
		FailureCode        *string                           `json:"failureCode"`
		UpdatedAt          time.Time                         `json:"updatedAt"`
		Proof              *rt.ReleaseQueryReadinessProof    `json:"proof"`
	}
	version := int64(0)
	deadline := time.Now().Add(15 * time.Second)
	for attempt := 0; ; attempt++ {
		key := fmt.Sprintf("joint-%d", attempt)
		status := call(search.URL, "/internal/search/release-preparations:prepare", "search.release.prepare", "content-service", key, command{binding, rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: source.Snapshot}, version, key}, &result)
		if status == 200 && result.Status == "completed" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("joint preparation failed", status)
		}
		var checkpoint struct {
			PreparationID  string                            `json:"preparationId"`
			Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
			SnapshotDigest string                            `json:"snapshotDigest"`
			Version        int64                             `json:"version"`
			Status         string                            `json:"status"`
			FailureCode    *string                           `json:"failureCode"`
			Proof          *rt.ReleaseQueryReadinessProof    `json:"proof"`
			UpdatedAt      time.Time                         `json:"updatedAt"`
		}
		q := struct {
			Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
			SnapshotDigest string                            `json:"snapshotDigest"`
		}{binding, source.Snapshot.SnapshotDigest}
		if status = call(search.URL, "/internal/search/release-preparations:query", "search.release.read", "content-service", "", q, &checkpoint); status != 200 {
			t.Fatal("checkpoint unavailable", status)
		}
		version = checkpoint.Version
		time.Sleep(100 * time.Millisecond)
	}
	if result.Proof == nil || result.Proof.Validate(binding, rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: source.Snapshot}) != nil {
		t.Fatal("joint proof drift")
	}
	if count, err := contentDB.Collection("data_release_state").CountDocuments(ctx, bson.M{}); err != nil || count != 0 {
		t.Fatal("prepare manufactured active pointer", count, err)
	}
	if count, err := contentDB.Collection("data_release_stage_receipts").CountDocuments(ctx, bson.M{}); err != nil || count != 0 {
		t.Fatal("prepare manufactured historical receipt", count, err)
	}
	for _, table := range []string{"user_profiles", "personas", "user_profile_search_outbox"} {
		var count int
		if err = pool.QueryRow(ctx, "SELECT count(*) FROM "+table).Scan(&count); err != nil || count != 0 {
			t.Fatal("Creator preparation wrote login authority", table, count, err)
		}
	}
	hidden, err := es.NewBackend(provider, provider.IndexName()).Recall(ctx, rt.RetrievePlan{Terms: []string{"联合旅行作者"}, Limit: 20})
	if err != nil || len(hidden) != 0 {
		t.Fatal("no-active candidate leaked", hidden, err)
	}
	if status := call(search.URL, "/internal/search/release-preparations:prepare", "search.release.prepare", "content-service", "", command{binding, rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: source.Snapshot}, 0, "missing-header"}, nil); status != 400 {
		t.Fatal("missing header accepted", status)
	}
	if status := call(user.URL, "/internal/user/creator-search-candidate:query", "wrong.scope", "content-service", "", query, nil); status != 403 {
		t.Fatal("wrong scope accepted", status)
	}
	wrong := source.Snapshot.SnapshotDigest
	q := struct {
		Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
		SnapshotDigest string                            `json:"snapshotDigest"`
	}{binding, "sha256:" + strings.Repeat("f", 64)}
	if q.SnapshotDigest == wrong {
		t.Fatal("invalid negative fixture")
	}
	if status := call(search.URL, "/internal/search/release-preparations:query", "search.release.read", "content-service", "", q, nil); status != 409 {
		t.Fatal("source digest drift accepted", status)
	}
	// completed query只读：重复读取前后checkpoint/proof和回执集合不变。
	var before bson.M
	if err = searchDB.Collection("search_release_preparations").FindOne(ctx, bson.M{"preparationId": binding.ID()}).Decode(&before); err != nil {
		t.Fatal(err)
	}
	receiptsBefore, _ := searchDB.Collection("search_release_preparation_receipts").CountDocuments(ctx, bson.M{})
	goodQuery := struct {
		Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
		SnapshotDigest string                            `json:"snapshotDigest"`
	}{binding, source.Snapshot.SnapshotDigest}
	if status := call(search.URL, "/internal/search/release-preparations:query", "search.release.read", "content-service", "", goodQuery, nil); status != 200 {
		t.Fatal("completed query failed", status)
	}
	var after bson.M
	_ = searchDB.Collection("search_release_preparations").FindOne(ctx, bson.M{"preparationId": binding.ID()}).Decode(&after)
	receiptsAfter, _ := searchDB.Collection("search_release_preparation_receipts").CountDocuments(ctx, bson.M{})
	beforeRaw, _ := json.Marshal(before)
	afterRaw, _ := json.Marshal(after)
	if !bytes.Equal(beforeRaw, afterRaw) || receiptsBefore != receiptsAfter {
		t.Fatal("proof query wrote state")
	}
	// 同一binding的新请求不能借合法重签摘要覆盖原User公开输入。
	drifted := *source.Snapshot
	drifted.SourceClosureDigest = "sha256:" + strings.Repeat("e", 64)
	if err = drifted.Seal(); err != nil {
		t.Fatal(err)
	}
	driftCommand := struct {
		Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
		Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
		ExpectedVersion int64                             `json:"expectedVersion"`
		IdempotencyKey  string                            `json:"idempotencyKey"`
	}{binding, rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &drifted}, result.PreparationVersion, "drift-input"}
	if status := call(search.URL, "/internal/search/release-preparations:prepare", "search.release.prepare", "content-service", "drift-input", driftCommand, nil); status != 409 {
		t.Fatal("same binding accepted new source bytes", status)
	}
	// User原candidate由owner精确重验，不因下游准备改写verifiedAt/closure。
	original, found, err := store.ReadVerifiedCandidate(ctx, identity)
	if err != nil || !found || original.ClosureDigest != state.ClosureDigest || !original.VerifiedAt.Equal(state.VerifiedAt) {
		t.Fatal("User candidate authority changed", err)
	}
	// 通过正式Provider重建动作仅改变独立测试write alias，查询必须拒绝旧proof。
	if _, err = provider.BeginRebuild(ctx); err != nil {
		t.Fatal(err)
	}
	if status := call(search.URL, "/internal/search/release-preparations:query", "search.release.read", "content-service", "", goodQuery, nil); status == 200 {
		t.Fatal("split alias accepted old proof")
	}
	t.Log("User actual candidate + PG reader -> unified Search bootstrap/handler -> real ES completed proof PASS; full Content four-source orchestration remains separate")
}
