package releaseimport_test

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	importer "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
// 未连接任何DB：统一入口须在首次索引/事务/写入之前拒绝未装配barrier。
func TestCreatorActivationRejectsUnboundImporterBeforeStorage(t *testing.T) {
	client, err := mongo.Connect(options.Client().ApplyURI("mongodb://127.0.0.1:1"))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Disconnect(context.Background())
	_, err = importer.ActivateImportedPostRelease(t.Context(), client.Database("unconnected_no_mutation"), "gamma", importer.ImportedReleaseBinding{SourceOwner: "qwq_data", ReleaseID: "candidate", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}, importer.ExpectedActiveRelease{Empty: true, SourceOwner: "qwq_data"}, time.Now())
	if !errors.Is(err, app.ErrReleaseQueryNotReady) {
		t.Fatalf("unbound CLI/importer bypassed barrier: %v", err)
	}
}
