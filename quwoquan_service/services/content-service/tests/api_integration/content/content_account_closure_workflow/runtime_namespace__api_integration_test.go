// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
package content_account_closure_workflow_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"quwoquan_service/internal/platform/testinfra"
	closure "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
)

// 本测试只给真实隔离Mongo创建前置，不伪造源creation或runtime开放证据。
func TestRuntimeNamespaceExclusiveCreationAndReadback(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("closure_allocation"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := runtime.Close(context.Background()); err != nil {
			t.Error(err)
		}
	})
	db := runtime.Database
	allocation, err := closure.CreateRuntimeNamespace(ctx, db, "gamma", "gamma-local")
	if err != nil {
		t.Fatal(err)
	}
	rows, digest, err := allocation.InitialClosure(ctx)
	if err != nil || len(rows) != 9 || len(digest) != 71 {
		t.Fatalf("closure rows=%d digest=%s err=%v", len(rows), digest, err)
	}
	for _, row := range rows {
		if row.RecordCount != 0 || len(row.PhysicalInstanceId) != len("mongodb-collection-uuid:")+32 {
			t.Fatalf("invalid readback: %+v", row)
		}
	}
	if _, err := closure.CreateRuntimeNamespace(ctx, db, "gamma", "gamma-local"); err == nil {
		t.Fatal("existing namespace accepted as new")
	}
	if err := allocation.VerifyIdentity(ctx); err != nil {
		t.Fatal(err)
	}
	// persistence/corruption专项直接写入；普通增长不得改变UUID身份。
	if _, err := db.Collection(closure.InboxCollection).InsertOne(ctx, bson.M{"_id": "isolated-corruption-probe"}); err != nil {
		t.Fatal(err)
	}
	if err := allocation.VerifyIdentity(ctx); err != nil {
		t.Fatalf("ordinary growth changed physical identity: %v", err)
	}
	if _, _, err := allocation.InitialClosure(ctx); err == nil {
		t.Fatal("nonempty initial closure accepted")
	}
	if err := db.Collection(closure.ClosedSubjectTombstoneCollection).Drop(ctx); err != nil {
		t.Fatal(err)
	}
	if err := db.CreateCollection(ctx, closure.ClosedSubjectTombstoneCollection); err != nil {
		t.Fatal(err)
	}
	if err := allocation.VerifyIdentity(ctx); err == nil {
		t.Fatal("replacement UUID accepted")
	}
}

func TestRuntimeNamespaceRejectsProductionAndPartialResources(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("closure_partial"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := runtime.Close(context.Background()); err != nil {
			t.Error(err)
		}
	})
	db := runtime.Database
	for _, pair := range [][2]string{{"prod", "prod-hosted"}, {"gamma", "alpha-local"}, {"test", "test-local"}} {
		if _, err := closure.CreateRuntimeNamespace(ctx, db, pair[0], pair[1]); err == nil {
			t.Fatalf("invalid target accepted: %v", pair)
		}
	}
	names, err := db.ListCollectionNames(ctx, bson.M{})
	if err != nil || len(names) != 0 {
		t.Fatalf("rejection created collections: %v %v", names, err)
	}
	if err := db.CreateCollection(ctx, closure.InboxCollection); err != nil {
		t.Fatal(err)
	}
	if _, err := closure.CreateRuntimeNamespace(ctx, db, "gamma", "gamma-local"); err == nil {
		t.Fatal("partial old namespace accepted")
	}
	names, err = db.ListCollectionNames(ctx, bson.M{})
	if err != nil || len(names) != 1 || names[0] != closure.InboxCollection {
		t.Fatalf("old resource changed: %v %v", names, err)
	}
}
