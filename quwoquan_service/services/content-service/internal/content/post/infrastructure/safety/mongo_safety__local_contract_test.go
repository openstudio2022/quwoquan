package safety

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"os"
	"quwoquan_service/internal/platform/testinfra"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"testing"
	"time"
)

func assertWriteConflict(t *testing.T, err error) {
	t.Helper()
	var server mongo.ServerError
	if !errors.As(err, &server) || !server.HasErrorCode(112) {
		t.Fatalf("expected actual Mongo WriteConflict(112), got %v", err)
	}
}

type isolatedAuthority struct{ blocked bool }

func (a *isolatedAuthority) VerifyRecovery(context.Context) error {
	if a.blocked {
		return app.ErrPostSafetyNotReady
	}
	return nil
}
func (a *isolatedAuthority) VerifySource(context.Context, string, string, string) error {
	return a.VerifyRecovery(context.Background())
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 测试authority不是正式部署资格；实际Mongo事务/写冲突不由替身模拟。
func TestPostSafetyRealMongo(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("post_safety"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, x := context.WithTimeout(context.Background(), 20*time.Second)
		defer x()
		_ = runtime.Close(c)
	}()
	authority := &isolatedAuthority{}
	m, err := New(runtime.Database, "alpha", []byte(strings.Repeat("s", 32)), authority)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = New(runtime.Database, "alpha", nil, authority); err == nil {
		t.Fatal("missing key allowed")
	}
	if err = m.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	txn := func(fn func(context.Context) error) error {
		s, e := runtime.Database.Client().StartSession()
		if e != nil {
			return e
		}
		defer s.EndSession(ctx)
		_, e = s.WithTransaction(ctx, func(tx context.Context) (any, error) { return nil, fn(tx) })
		return e
	}
	digest := "sha256:" + strings.Repeat("a", 64)
	var member app.PostSafetyMember
	if _, err = m.Read(ctx, "qwq_data", "post"); !errors.Is(err, app.ErrPostSafetyNotReady) {
		t.Fatal("missing interpreted safe", err)
	}
	if err = txn(func(tx context.Context) error {
		var e error
		member, e = m.Initialize(tx, "qwq_data", "post", 1, "allowed", "verified_source", digest)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error { return m.TouchAllowed(tx, []app.PostSafetyMember{member}) }); err != nil {
		t.Fatal(err)
	}
	// CAS事务先锁定安全行，另一个撤权事务产生真实写冲突并最终在CAS提交后生效。
	s1, _ := runtime.Database.Client().StartSession()
	defer s1.EndSession(ctx)
	if err = s1.StartTransaction(); err != nil {
		t.Fatal(err)
	}
	tx1 := mongo.NewSessionContext(ctx, s1)
	if err = m.TouchAllowed(tx1, []app.PostSafetyMember{member}); err != nil {
		t.Fatal(err)
	}
	// 显式事务屏障：winner保持未提交写锁，loser必须先收到真实Mongo WriteConflict。
	s2, e := runtime.Database.Client().StartSession()
	if e != nil {
		t.Fatal(e)
	}
	defer s2.EndSession(ctx)
	if e = s2.StartTransaction(); e != nil {
		t.Fatal(e)
	}
	_, e = m.Decide(mongo.NewSessionContext(ctx, s2), "qwq_data", "post", 1, 2, "restricted", "moderation_rejected", "sha256:"+strings.Repeat("b", 64))
	assertWriteConflict(t, e)
	_ = s2.AbortTransaction(ctx)
	if err = s1.CommitTransaction(ctx); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 1, 2, "restricted", "moderation_rejected", "sha256:"+strings.Repeat("b", 64))
		return e
	}); err != nil {
		t.Fatal(err)
	}
	// 反序：安全事务先占同键写锁，CAS先冲突；安全提交后重新执行必须not-ready。
	var reverse app.PostSafetyMember
	if err = txn(func(tx context.Context) error {
		var e error
		reverse, e = m.Initialize(tx, "qwq_data", "reverse", 1, "allowed", "verified_source", digest)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	if err = s1.StartTransaction(); err != nil {
		t.Fatal(err)
	}
	_, err = m.Decide(mongo.NewSessionContext(ctx, s1), "qwq_data", "reverse", 1, 2, "restricted", "moderation_rejected", digest)
	if err != nil {
		t.Fatal(err)
	}
	if err = s2.StartTransaction(); err != nil {
		t.Fatal(err)
	}
	err = m.TouchAllowed(mongo.NewSessionContext(ctx, s2), []app.PostSafetyMember{reverse})
	assertWriteConflict(t, err)
	_ = s2.AbortTransaction(ctx)
	if err = s1.CommitTransaction(ctx); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error { return m.TouchAllowed(tx, []app.PostSafetyMember{reverse}) }); !errors.Is(err, app.ErrPostSafetyNotReady) {
		t.Fatal("safety-first CAS accepted", err)
	}
	if err = txn(func(tx context.Context) error { return m.TouchAllowed(tx, []app.PostSafetyMember{member}) }); !errors.Is(err, app.ErrPostSafetyNotReady) {
		t.Fatal("safety winner did not reject old candidate", err)
	}
	// 同identity同决定重放和同版本不同摘要；授权恢复不恢复旧candidate的revision。
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 1, 2, "restricted", "moderation_rejected", "sha256:"+strings.Repeat("b", 64))
		return e
	}); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 2, 2, "restricted", "moderation_rejected", digest)
		return e
	}); err == nil {
		t.Fatal("same version different digest")
	}
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 2, 3, "allowed", "authorized_reallow", digest)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error { return m.TouchAllowed(tx, []app.PostSafetyMember{member}) }); err == nil {
		t.Fatal("old candidate restored")
	}
	rolled := errors.New("force atomic abort")
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 3, 4, "terminated", "purged", digest)
		if e != nil {
			return e
		}
		return rolled
	}); !errors.Is(err, rolled) {
		t.Fatal(err)
	}
	if _, err = m.Read(ctx, "qwq_data", "post"); err != nil {
		t.Fatal("abort leaked safety", err)
	}
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 3, 4, "terminated", "purged", digest)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	if err = txn(func(tx context.Context) error {
		_, e := m.Decide(tx, "qwq_data", "post", 4, 99, "allowed", "authorized_reallow", digest)
		return e
	}); err == nil {
		t.Fatal("terminal revived")
	}
	authority.blocked = true
	if _, err = m.Read(ctx, "qwq_data", "post"); err == nil {
		t.Fatal("missing recovery allowed")
	}
	var row bson.M
	if err = runtime.Database.Collection(Collection).FindOne(ctx, bson.M{}).Decode(&row); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"postId", "authorId", "payload", "title", "body", "expireAt"} {
		if _, ok := row[key]; ok {
			t.Fatal("forbidden retained field", key)
		}
	}
}
