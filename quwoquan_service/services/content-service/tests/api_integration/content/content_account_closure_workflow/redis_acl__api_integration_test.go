// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
package content_account_closure_workflow_test

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"testing"
	"time"

	goredis "github.com/redis/go-redis/v9"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/servicekit"
	closure "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
)

func TestProductionGoRedisNamedACLStreamCommands(t *testing.T) {
	t.Setenv("TEST_REDIS_ADDR", "")
	t.Setenv("QWQ_TEST_REDIS_ADDR", "")
	ctx, cancel := context.WithTimeout(t.Context(), 60*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := runtime.Close(context.Background()); err != nil {
			t.Error(err)
		}
	})
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	password := hex.EncodeToString(key)
	admin := goredis.NewClient(&goredis.Options{Addr: runtime.Addr, Password: runtime.Password})
	defer admin.Close()
	if err := admin.Do(ctx, "ACL", "SETUSER", "isolated_owner", "reset", "on", ">"+password, "~"+closure.UserAccountEventStream, "+ping", "+xadd", "+xautoclaim", "+xgroup", "+xreadgroup", "+xack", "+xrange", "+xpending", "+xinfo", "(~"+closure.DeadLetterStream+" +xadd +expire)").Err(); err != nil {
		t.Fatal(err)
	}
	if err := admin.Do(ctx, "ACL", "SETUSER", "default", "off").Err(); err != nil {
		t.Fatal(err)
	}
	// 与正式User/Content相同servicekit→runtime→platform构造链，不直接用goredis作正例。
	router, _, err := servicekit.NewRedisRouter(map[string]servicekit.RedisSceneConfig{"general": {Mode: "standalone", Addr: runtime.Addr, Username: "isolated_owner", Password: password}})
	if err != nil {
		t.Fatal(err)
	}
	defer router.Close()
	source := router.Scene("general")
	if err := source.Ping(ctx); err != nil {
		t.Fatal(err)
	}
	if err := source.XGroupCreateMkStream(ctx, closure.UserAccountEventStream, closure.ConsumerGroup, "0-0"); err != nil {
		t.Fatal(err)
	}
	if _, _, err := source.XAutoClaim(ctx, closure.UserAccountEventStream, closure.ConsumerGroup, "probe", time.Millisecond, "0-0", 10); err != nil {
		t.Fatal(err)
	}
	id, err := source.XAdd(ctx, closure.UserAccountEventStream, map[string]string{"isolatedTransportProbe": "not-a-business-event"})
	if err != nil {
		t.Fatal(err)
	}
	messages, err := source.XReadGroup(ctx, closure.ConsumerGroup, "probe", map[string]string{closure.UserAccountEventStream: ">"}, 1, time.Millisecond)
	if err != nil || len(messages) != 1 {
		t.Fatalf("read count=%d err=%v", len(messages), err)
	}
	if err := source.XAck(ctx, closure.UserAccountEventStream, closure.ConsumerGroup, id); err != nil {
		t.Fatal(err)
	}
	if _, err := source.XAdd(ctx, closure.DeadLetterStream, map[string]string{"errorDigest": "isolated-non-pii-probe"}); err != nil {
		t.Fatal(err)
	}
	if err := source.Expire(ctx, closure.DeadLetterStream, time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := source.Expire(ctx, closure.UserAccountEventStream, time.Minute); err == nil {
		t.Fatal("source TTL mutation allowed")
	}
	if _, err := source.XAdd(ctx, "unrelated", map[string]string{"probe": "no"}); err == nil {
		t.Fatal("unrelated key accepted")
	}
	for _, user := range []string{"", "wrong-owner"} {
		invalid, _, err := servicekit.NewRedisRouter(map[string]servicekit.RedisSceneConfig{"general": {Mode: "standalone", Addr: runtime.Addr, Username: user, Password: password}})
		if err != nil {
			continue
		}
		err = invalid.Scene("general").Ping(ctx)
		invalid.Close()
		if err == nil {
			t.Fatal("missing/wrong named ACL fell back to default")
		}
	}
}
