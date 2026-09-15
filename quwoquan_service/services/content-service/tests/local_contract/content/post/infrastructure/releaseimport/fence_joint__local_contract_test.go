package releaseimport_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http"
	"net/http/httptest"
	"os"
	"quwoquan_service/generated/operationsecurity"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	rtredis "quwoquan_service/runtime/redis"
	rt "quwoquan_service/runtime/search"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	public "quwoquan_service/services/content-service/internal/content/post/application/public"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	messaging "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	persistence "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 私有事务fixture端点不编入生产程序；业务receipt/fence使用真实签名与generated runtime guard。
func TestFenceJointContentHarness(t *testing.T) {
	addr := os.Getenv("QWQ_FENCE_JOINT_REDIS")
	if addr == "" {
		t.Skip("joint runner required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 240*time.Second)
	defer cancel()
	db, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("fence_joint_content"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { c, x := context.WithTimeout(context.Background(), 20*time.Second); defer x(); _ = db.Close(c) }()
	router := platformredis.MustNewRouter(rtredis.RouterConfig{Scenes: map[string]rtredis.SceneConfig{"general": {Mode: "standalone", Addr: addr}}, DefaultScene: "general"})
	defer router.Close()
	publisher := messaging.NewPostLifecycleStreamPublisher(router.Scene("general"))
	now := time.Now().UTC().Truncate(time.Millisecond)
	targets := map[string]ImportedReleaseBinding{}
	for _, name := range []string{"a", "b"} {
		opts := ImportOptions{ReleaseID: "joint-" + name, ManifestDigest: "sha256:" + strings.Repeat(name, 64), ReleaseKind: "content", ActivationMode: "stage-only", Mode: "sync", DeletePolicy: "tombstone", SourceOwner: "qwq_data"}
		p := PostDoc{PostRef: "posts/article/joint-" + name, ContentID: "joint-" + name, ContentVersion: 1, PoolSourceType: "data", VariantPurpose: "original", PoolStatus: "active", ContentType: "article", ContentIdentity: "work", Title: "联合验证" + name, AuthorID: "joint-author", ArticleMarkdown: "# 联合验证", Admission: ContentAdmission{ProcessResult: "completed", QualityResult: "passed", UsageScope: "production", EvidenceRef: "audit/test", EvidenceDigest: "sha256:" + strings.Repeat("a", 64)}, CreatedAt: now.Add(-time.Hour), UpdatedAt: now, PublishedAt: now}
		media := map[string]ReleaseMediaAsset{"joint-asset-" + name: {AssetID: "joint-asset-" + name, Kind: "image", Version: 1, ContentType: "image/jpeg", PublicSliceKey: "media/image/s/asset/joint-" + name + "/source.jpg", SHA256: "sha256:" + strings.Repeat("9", 64), Bytes: 1}}
		if _, err = StageImportedPostRelease(ctx, db.Database, "alpha", []PostDoc{p}, media, now, opts); err != nil {
			t.Fatal(err)
		}
		targets[name] = ReleaseBindingFromImportOptions(opts)
	}
	config := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x64}, 32), Issuer: "joint-fence", Audience: "content-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, err := auth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	ownerMux := http.NewServeMux()
	httpadapter.NewReleaseCommitReceiptHandler(NewCommitReceiptReader(db.Database, "alpha"), "alpha").Register(ownerMux)
	httpadapter.NewActiveReleaseFenceHandler(persistence.NewMongoActiveSupplyReader(db.Database, "alpha"), "alpha").Register(ownerMux)
	guarded := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("content"))(httpadapter.RequireSensitiveOperationPrincipal(ownerMux)))
	mux := http.NewServeMux()
	mux.Handle("/internal/", guarded)
	done := make(chan struct{}, 1)
	reply := func(w http.ResponseWriter, v any) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(v)
	}
	failReceipts := false
	mux.HandleFunc("/fixture/activate", func(w http.ResponseWriter, r *http.Request) {
		target, ok := targets[r.URL.Query().Get("target")]
		if !ok {
			http.Error(w, "target", 400)
			return
		}
		before, e := ReadActiveImportedPostRelease(ctx, db.Database, "alpha", "qwq_data")
		if e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		expected := ExpectedActiveRelease{Empty: !before.Found, SourceOwner: "qwq_data", ReleaseID: before.ReleaseID, ManifestDigest: before.ManifestDigest, Revision: before.Revision}
		result, e := activateForTest(ctx, db.Database, "alpha", target, expected, time.Now().UTC())
		if e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		eventID := public.ReleaseFenceEventID(wireFence(result.Active))
		var record outboxDocument
		if e = db.Database.Collection("content_outbox").FindOne(ctx, bson.M{"_id": eventID}).Decode(&record); e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		event := postports.OutboxEvent{EventID: record.ID, EventType: record.EventType, AggregateType: record.AggregateType, AggregateID: record.AggregateID, AggregateVersion: record.AggregateVersion, Payload: record.PayloadJSON, OccurredAt: record.OccurredAt}
		if e = publisher.Publish(ctx, event); e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		reply(w, map[string]any{"eventId": eventID, "revision": result.Active.Revision, "target": target.ReleaseID})
	})
	mux.HandleFunc("/fixture/snapshots", func(w http.ResponseWriter, r *http.Request) { reply(w, targets) })
	mux.HandleFunc("/fixture/stats", func(w http.ResponseWriter, r *http.Request) {
		result := map[string]string{}
		for _, name := range []string{"data_release_state", "data_release_candidate_posts", "data_release_candidate_media_assets", "posts", "media_assets"} {
			cur, e := db.Database.Collection(name).Find(ctx, bson.M{}, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
			if e != nil {
				http.Error(w, e.Error(), 500)
				return
			}
			var rows []bson.M
			e = cur.All(ctx, &rows)
			_ = cur.Close(ctx)
			if e != nil {
				http.Error(w, e.Error(), 500)
				return
			}
			raw, _ := bson.MarshalExtJSON(bson.M{"rows": rows}, true, false)
			result[name] = string(raw)
		}
		reply(w, result)
	})
	mux.HandleFunc("/fixture/receipt-mode", func(w http.ResponseWriter, r *http.Request) {
		failReceipts = r.URL.Query().Get("fail") == "1"
		w.WriteHeader(204)
	})
	mux.HandleFunc("/fixture/incomplete", func(w http.ResponseWriter, r *http.Request) {
		_, e := db.Database.Collection("data_release_stage_receipts").UpdateOne(ctx, bson.M{"eventId": r.URL.Query().Get("eventId")}, bson.M{"$unset": bson.M{"transition": ""}})
		if e != nil {
			http.Error(w, e.Error(), 500)
			return
		}
		w.WriteHeader(204)
	})
	mux.HandleFunc("/fixture/done", func(w http.ResponseWriter, r *http.Request) {
		select {
		case done <- struct{}{}:
		default:
		}
		w.WriteHeader(204)
	})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if failReceipts && r.URL.Path == "/internal/content/release-commit-receipts:query" {
			http.Error(w, "injected disconnected receipt", 503)
			return
		}
		mux.ServeHTTP(w, r)
	}))
	defer server.Close()
	fmt.Printf("CONTENT_FENCE_JOINT_READY %s\n", server.URL)
	select {
	case <-done:
	case <-ctx.Done():
		t.Fatal("joint runner deadline", ctx.Err())
	}
}

func activateForTest(ctx context.Context, database *mongo.Database, environment string, target ImportedReleaseBinding, expected ExpectedActiveRelease, activatedAt time.Time) (ReleaseActivationResult, error) {
	barrier, err := public.NewReleaseQueryBarrier(allowRequiredReleaseQueries{})
	if err != nil {
		return ReleaseActivationResult{}, err
	}
	return ActivateImportedPostRelease(public.WithReleaseQueryBarrier(ctx, barrier), database, environment, target, expected, activatedAt)
}

type allowRequiredReleaseQueries struct{}

func (allowRequiredReleaseQueries) VerifyRequiredQueries(context.Context, rt.ReleaseCandidateBinding) error {
	return nil
}

func wireFence(value ActiveReleaseBinding) wire.ContentActiveReleaseFence {
	result := wire.ContentActiveReleaseFence{Found: value.Found, Environment: value.Environment, SourceOwner: value.SourceOwner, ReleaseId: value.ReleaseID, ManifestDigest: value.ManifestDigest, Revision: value.Revision, ProjectionVersion: value.ProjectionVersion}
	if value.Found {
		activatedAt := value.ActivatedAt
		result.ActivatedAt = &activatedAt
	}
	return result
}

type outboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateType    string    `bson:"aggregateType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	PayloadJSON      []byte    `bson:"payloadJson"`
	OccurredAt       time.Time `bson:"occurredAt"`
}
