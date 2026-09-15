package releaseimport

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"sync"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 合法白盒私有事务证据，显式独立Mongo开关；绝非完整admission/保护PASS。
func TestPrivateFenceTransactionMongo(t *testing.T) {
	if os.Getenv("QWQ_FENCE_TX_REAL_MONGO") != "1" {
		t.Skip("explicit isolated Mongo transaction test")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 150*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("fence_private"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, x := context.WithTimeout(context.Background(), 30*time.Second)
		defer x()
		_ = runtime.Close(c)
	}()
	db := runtime.Database
	now := time.Now().UTC().Truncate(time.Millisecond)
	stage := func(id string) ImportedReleaseBinding {
		opts := ImportOptions{ReleaseID: id, ManifestDigest: "sha256:" + strings.Repeat(string(id[len(id)-1]), 64), ReleaseKind: "content", ActivationMode: "stage-only", Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data"}
		post := PostDoc{PostRef: "posts/article/" + id + "/1", ContentID: "content-" + id, ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", PoolStatus: "active", ContentType: "article", ContentIdentity: "work", Title: id, AuthorID: "builtin_travel_blogger", ArticleMarkdown: "# " + id, Admission: ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "production", EvidenceRef: "audit/attestation.json", EvidenceDigest: "sha256:" + strings.Repeat("a", 64)}, CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now}
		media := map[string]ReleaseMediaAsset{"asset-" + id: {AssetID: "asset-" + id, Kind: "image", Version: 1, ContentType: "image/jpeg", PublicSliceKey: "media/image/s/asset/" + id + "/source.jpg", SHA256: "sha256:" + strings.Repeat("9", 64), Bytes: 128}}
		if _, err := StageImportedPostRelease(ctx, db, "alpha", []PostDoc{post}, media, now, opts); err != nil {
			t.Fatal("stage", err)
		}
		return ReleaseBindingFromImportOptions(opts)
	}
	a, b := stage("release-a"), stage("release-b")
	empty := ExpectedActiveRelease{Empty: true, SourceOwner: "qwq_data"}
	if _, err = ActivateImportedPostRelease(ctx, db, "alpha", a, empty, now); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatal("production admission bypass", err)
	}
	candidateBefore, err := db.Collection("data_release_candidate_posts").FindOne(ctx, bson.M{"releaseId": a.ReleaseID}).Raw()
	if err != nil {
		t.Fatal(err)
	}
	saved := append(bson.Raw{}, candidateBefore...)
	first, err := activateImportedPostReleaseTransaction(ctx, db, "alpha", a, empty, now)
	if err != nil {
		t.Fatal("A", err)
	}
	if first.Active.Revision != 1 || first.OutboxEventsReady != 1 {
		t.Fatal(first)
	}
	read := NewCommitReceiptReader(db, "alpha")
	// 真实signer+生产runtime guard+真实Mongo reader，仍不绕过activation admission。
	config := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x64}, 32), Issuer: "receipt-mongo", Audience: "content-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, e := auth.NewHS256Verifier(config)
	if e != nil {
		t.Fatal(e)
	}
	mux := http.NewServeMux()
	httpadapter.NewReleaseCommitReceiptHandler(read, "alpha").Register(mux)
	guarded := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("content"))(httpadapter.RequireSensitiveOperationPrincipal(mux)))
	httpReceipt := func(q wire.ReadContentReleaseCommitReceiptQuery, scope string) int {
		raw, _ := json.Marshal(q)
		request := httptest.NewRequest(http.MethodPost, "/internal/content/release-commit-receipts:query", bytes.NewReader(raw))
		if scope != "" {
			signer, e := auth.NewHS256ServiceAuthorizationProvider(config, "search-service", []string{scope})
			if e != nil {
				t.Fatal(e)
			}
			header, e := signer.AuthorizationHeader(ctx)
			if e != nil {
				t.Fatal(e)
			}
			request.Header.Set("Authorization", header)
		}
		response := httptest.NewRecorder()
		guarded.ServeHTTP(response, request)
		return response.Code
	}
	query := func(target ImportedReleaseBinding, before ActiveReleaseBinding) wire.ReadContentReleaseCommitReceiptQuery {
		return wire.ReadContentReleaseCommitReceiptQuery{Release: wire.ReleaseCandidateBinding{Environment: "alpha", SourceOwner: target.SourceOwner, ReleaseId: target.ReleaseID, ManifestDigest: target.ManifestDigest}, Expected: releaseWireFence(before)}
	}
	q := query(a, ActiveReleaseBinding{Environment: "alpha", SourceOwner: "qwq_data"})
	if code := httpReceipt(q, ""); code != 401 {
		t.Fatal("unsigned receipt", code)
	}
	if code := httpReceipt(q, "wrong.scope"); code != 403 {
		t.Fatal("wrong scope receipt", code)
	}
	if code := httpReceipt(q, "content.release.fence.read"); code != 200 {
		t.Fatal("signed Mongo receipt", code)
	}
	receipt, err := read.ReadContentReleaseCommitReceipt(ctx, q)
	if err != nil {
		t.Fatal("receipt", err)
	}
	// 实际Python出站signer/HTTP client跨到Go生产guard与真实Mongo receipt。
	if python := os.Getenv("QWQ_FENCE_REC_PYTHON"); python != "" {
		server := httptest.NewServer(guarded)
		defer server.Close()
		root, _ := filepath.Abs(filepath.Join("..", "..", "..", "..", "..", "..", ".."))
		raw, _ := json.Marshal(receipt)
		script := `import sys,json
sys.path.insert(0,sys.argv[1]+"/services/recommendation-service")
from internal.recommendation.recommendation_candidate_index_view.infrastructure.fence_reconciliation import ContentReceiptClient,content_service_authorization
from generated.recommendation.recommendation_candidate_index_view.events.content_post_ContentReleaseFenceChanged import ContentActiveReleaseFence,ContentReleaseFenceChangedPayload
from internal.recommendation.recommendation_candidate_index_view.application.fence_reconciliation import content_payload_digest
expected=json.loads(sys.argv[3]);event=ContentReleaseFenceChangedPayload.model_validate(expected["transition"])
assert content_payload_digest(event)==expected["payloadDigest"]
client=ContentReceiptClient(sys.argv[2],content_service_authorization(),ContentActiveReleaseFence)
actual=client.read_commit(expected["transition"]["after"],expected["transition"]["before"])
assert actual==expected
print("PYTHON_SIGNER_TO_GO_GUARD_REAL_MONGO_RECEIPT_PASS")`
		cmd := exec.Command(python, "-B", "-c", script, root, server.URL, string(raw))
		cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1", "AUTH_JWT_SECRET="+strings.Repeat("d", 32), "AUTH_JWT_ISSUER=receipt-mongo", "AUTH_JWT_AUDIENCE=content-service", "AUTH_JWT_TOKEN_VERSION=1")
		if output, e := cmd.CombinedOutput(); e != nil {
			t.Fatalf("Python signer real receipt %v %s", e, output)
		} else {
			t.Log(string(output))
		}
	}
	replay, err := activateImportedPostReleaseTransaction(ctx, db, "alpha", a, empty, now.Add(time.Second))
	if err != nil || !replay.Replayed {
		t.Fatal("replay", replay, err)
	}
	expected := ExpectedActiveRelease{SourceOwner: "qwq_data", ReleaseID: a.ReleaseID, ManifestDigest: a.ManifestDigest, Revision: 1}
	// outbox/receipt失败及live唯一索引冲突都必须回滚pointer与live，不能生成部分事件。
	for _, collection := range []string{"content_outbox", "data_release_stage_receipts"} {
		if err = db.RunCommand(ctx, bson.D{{Key: "collMod", Value: collection}, {Key: "validator", Value: bson.M{"rejectNewFence": bson.M{"$exists": true}}}}).Err(); err != nil {
			t.Fatal(err)
		}
		if _, err = activateImportedPostReleaseTransaction(ctx, db, "alpha", b, expected, now.Add(2*time.Second)); err == nil {
			t.Fatal("failure injection accepted", collection)
		}
		if err = db.RunCommand(ctx, bson.D{{Key: "collMod", Value: collection}, {Key: "validator", Value: bson.M{}}}).Err(); err != nil {
			t.Fatal(err)
		}
		active, e := ReadActiveImportedPostRelease(ctx, db, "alpha", "qwq_data")
		if e != nil || active.ReleaseID != a.ReleaseID || active.Revision != 1 {
			t.Fatal("partial pointer", active, e)
		}
		if n, e := db.Collection("posts").CountDocuments(ctx, bson.M{"releaseId": b.ReleaseID}); e != nil || n != 0 {
			t.Fatal("partial live", n, e)
		}
	}
	if _, err = db.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "authorId", Value: 1}}, Options: options.Index().SetName("test_materialization_conflict").SetUnique(true)}); err != nil {
		t.Fatal(err)
	}
	if _, err = activateImportedPostReleaseTransaction(ctx, db, "alpha", b, expected, now.Add(2*time.Second)); err == nil {
		t.Fatal("materialize failure accepted")
	}
	if err = db.Collection("posts").Indexes().DropOne(ctx, "test_materialization_conflict"); err != nil {
		t.Fatal(err)
	}
	second, err := activateImportedPostReleaseTransaction(ctx, db, "alpha", b, expected, now.Add(2*time.Second))
	if err != nil {
		t.Fatal("B", err)
	}
	var old bson.M
	if err = db.Collection("posts").FindOne(ctx, bson.M{"releaseId": a.ReleaseID}).Decode(&old); err != nil {
		t.Fatal(err)
	}
	if old["status"] == "deleted" || old["deletedAt"] != nil || old["lifecycleStatus"] != "inactive" {
		t.Fatal("release exit became authoritative deletion", old)
	}
	if _, err = read.ReadContentReleaseCommitReceipt(ctx, q); err != nil {
		t.Fatal("history exact receipt must survive newer pointer", err)
	}
	if code := httpReceipt(q, "content.release.fence.read"); code != 200 {
		t.Fatal("signed history after pointer advanced", code)
	}
	var media bson.M
	if err = db.Collection("media_assets").FindOne(ctx, bson.M{"_id": "asset-" + a.ReleaseID}).Decode(&media); err != nil {
		t.Fatal(err)
	}
	if media["processingStatus"] != "ready" || media["deletedAt"] != nil {
		t.Fatal("release exit deleted media", media)
	}
	candidateAfter, err := db.Collection("data_release_candidate_posts").FindOne(ctx, bson.M{"releaseId": a.ReleaseID}).Raw()
	if err != nil || string(candidateAfter) != string(saved) {
		t.Fatal("A candidate changed", err)
	}
	expectedB := ExpectedActiveRelease{SourceOwner: "qwq_data", ReleaseID: b.ReleaseID, ManifestDigest: b.ManifestDigest, Revision: second.Active.Revision}
	third, err := activateImportedPostReleaseTransaction(ctx, db, "alpha", a, expectedB, now.Add(3*time.Second))
	if err != nil || third.Active.Revision != 3 {
		t.Fatal("rollback", third, err)
	}
	if n, e := db.Collection("content_outbox").CountDocuments(ctx, bson.M{}); e != nil || n != 3 {
		t.Fatal("exact one transition each", n, e)
	}
	if n, e := db.Collection("content_outbox").CountDocuments(ctx, bson.M{"eventType": bson.M{"$ne": "ContentReleaseFenceChanged"}}); e != nil || n != 0 {
		t.Fatal("fake Post lifecycle", n, e)
	}
	// 同attempt原回执摘要损坏必须拒绝，历史缺字段同样not-ready，不推导补字段。
	key := bson.M{"eventId": receipt.EventId}
	_, err = db.Collection("data_release_stage_receipts").UpdateOne(ctx, key, bson.M{"$set": bson.M{"payloadDigest": "sha256:" + strings.Repeat("0", 64)}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = read.ReadContentReleaseCommitReceipt(ctx, q); !errors.Is(err, app.ErrReleaseQueryInvalid) {
		t.Fatal("tampered receipt accepted", err)
	}
	_, _ = db.Collection("data_release_stage_receipts").UpdateOne(ctx, key, bson.M{"$unset": bson.M{"transition": ""}})
	if _, err = read.ReadContentReleaseCommitReceipt(ctx, q); !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatal("old receipt invented", err)
	}
	if code := httpReceipt(q, "content.release.fence.read"); code != 409 {
		t.Fatal("signed old incomplete receipt not rejected", code)
	}
	// 真竞争：同expected的不同目标只有一次成功，败方保持冲突；不注入admission替身。
	c := stage("release-c")
	d := stage("release-d")
	before := ExpectedActiveRelease{SourceOwner: "qwq_data", ReleaseID: a.ReleaseID, ManifestDigest: a.ManifestDigest, Revision: 3}
	results := make(chan error, 2)
	var wg sync.WaitGroup
	for _, target := range []ImportedReleaseBinding{c, d} {
		wg.Add(1)
		go func(target ImportedReleaseBinding) {
			defer wg.Done()
			_, e := activateImportedPostReleaseTransaction(ctx, db, "alpha", target, before, now.Add(4*time.Second))
			results <- e
		}(target)
	}
	wg.Wait()
	close(results)
	ok, conflict := 0, 0
	for e := range results {
		if e == nil {
			ok++
		} else {
			var typed *ReleaseActivationCASConflictError
			if !errors.As(e, &typed) {
				t.Fatal(e)
			}
			conflict++
		}
	}
	if ok != 1 || conflict != 1 {
		t.Fatal(ok, conflict)
	}
	raw, _ := json.Marshal(receipt.Transition)
	var shape map[string]any
	_ = json.Unmarshal(raw, &shape)
	if len(shape) != 2 {
		t.Fatal("event not exact before/after")
	}
}
