// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-002
package servicekit

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rthealth "quwoquan_service/runtime/health"
)

// mongoClientDouble 是窄投影的同包 typed double：只验证编排（连接、健康
// 检查、清理注册），不触真实 Mongo；double 不出测试树。
type mongoClientDouble struct {
	pings       int
	disconnects int
	pingErr     error
	ping        func(context.Context) error
}

func (double *mongoClientDouble) Ping(ctx context.Context) error {
	double.pings++
	if double.ping != nil {
		return double.ping(ctx)
	}
	return double.pingErr
}

func (double *mongoClientDouble) Disconnect(context.Context) error {
	double.disconnects++
	return nil
}

func (double *mongoClientDouble) Database(string) rtmongo.Database {
	return nil
}

func mongoTestAssembly(connect mongoConnectFunc) *Assembly {
	return &Assembly{
		Identity:     Identity{ServiceName: "tag-service", AppEnv: "alpha"},
		Health:       rthealth.NewChecker(),
		Workers:      &WorkerRegistry{},
		Cleanups:     &CleanupStack{},
		Context:      context.Background(),
		mongoConnect: connect,
	}
}

func TestAssemblyMongoFailsClosedOnMissingDeclaration(t *testing.T) {
	assembly := mongoTestAssembly(func(context.Context, rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		t.Fatal("connect must not run without a complete declaration")
		return nil, nil
	})

	if _, err := assembly.Mongo(MongoConfig{Database: "quwoquan_tag"}); err == nil ||
		!strings.Contains(err.Error(), "mongo.uri is required") {
		t.Fatalf("expected uri fail-closed, got %v", err)
	}
	if _, err := assembly.Mongo(MongoConfig{URI: "mongodb://db:27017"}); err == nil ||
		!strings.Contains(err.Error(), "mongo.database is required") {
		t.Fatalf("expected database fail-closed, got %v", err)
	}
}

func TestAssemblyMongoPropagatesConnectFailure(t *testing.T) {
	connectErr := errors.New("connection refused")
	assembly := mongoTestAssembly(func(context.Context, rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		return nil, connectErr
	})
	if _, err := assembly.Mongo(MongoConfig{
		URI: "mongodb://db:27017", Database: "quwoquan_tag",
	}); err == nil || !errors.Is(err, connectErr) {
		t.Fatalf("expected connect failure propagation, got %v", err)
	}
}

func TestAssemblyMongoRegistersHealthAndCleanup(t *testing.T) {
	double := &mongoClientDouble{}
	var seenURI string
	assembly := mongoTestAssembly(func(_ context.Context, cfg rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		seenURI = cfg.URI
		return double, nil
	})

	if _, err := assembly.Mongo(MongoConfig{
		URI: "mongodb://db:27017", Database: "quwoquan_tag",
	}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if seenURI != "mongodb://db:27017" {
		t.Fatalf("declared uri must reach the connector, got %q", seenURI)
	}

	result := assembly.Health.Check(context.Background())
	if _, registered := result.Checks["mongodb"]; !registered {
		t.Fatalf("expected mongodb health check registration, got %v", result.Checks)
	}
	if double.pings == 0 {
		t.Fatal("health check must ping the connected client")
	}

	if err := assembly.Cleanups.Close(context.Background()); err != nil {
		t.Fatalf("unexpected cleanup error: %v", err)
	}
	if double.disconnects != 1 {
		t.Fatalf("cleanup must disconnect exactly once, got %d", double.disconnects)
	}
}

func TestAssemblyMongoWithReadinessTimeoutRegistersSingleTimedCheck(t *testing.T) {
	const readinessTimeout = 25 * time.Millisecond
	var connectCalls int
	deadlineSeen := make(chan time.Time, 1)
	double := &mongoClientDouble{
		ping: func(ctx context.Context) error {
			deadline, ok := ctx.Deadline()
			if !ok {
				return errors.New("mongodb readiness context has no deadline")
			}
			deadlineSeen <- deadline
			<-ctx.Done()
			return ctx.Err()
		},
	}
	assembly := mongoTestAssembly(func(context.Context, rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		connectCalls++
		return double, nil
	})

	startedAt := time.Now()
	if _, err := assembly.MongoWithReadinessTimeout(MongoConfig{
		URI: "mongodb://db:27017", Database: "quwoquan_tag",
	}, readinessTimeout); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	result := assembly.Health.Check(context.Background())

	if connectCalls != 1 {
		t.Fatalf("mongo component must connect exactly once, got %d", connectCalls)
	}
	if len(result.Checks) != 1 || result.Checks["mongodb"] != context.DeadlineExceeded.Error() {
		t.Fatalf("expected one timed mongodb check without registration error, got %v", result.Checks)
	}
	if result.Status != "degraded" {
		t.Fatalf("timed out mongodb check must degrade readiness, got %q", result.Status)
	}
	deadline := <-deadlineSeen
	if budget := deadline.Sub(startedAt); budget < readinessTimeout-10*time.Millisecond ||
		budget > readinessTimeout+50*time.Millisecond {
		t.Fatalf("mongodb check did not receive the custom readiness window: %v", budget)
	}
	if elapsed := time.Since(startedAt); elapsed > 250*time.Millisecond {
		t.Fatalf("custom readiness check exceeded bounded test window: %v", elapsed)
	}
	if double.pings != 1 {
		t.Fatalf("mongodb health check must run exactly once, got %d", double.pings)
	}

	if err := assembly.Cleanups.Close(context.Background()); err != nil {
		t.Fatalf("unexpected cleanup error: %v", err)
	}
	if double.disconnects != 1 {
		t.Fatalf("custom-timeout component must register one cleanup, got %d", double.disconnects)
	}
}

func TestAssemblyMongoWithReadinessTimeoutDefaultsInvalidBudget(t *testing.T) {
	for _, invalidTimeout := range []time.Duration{0, -time.Millisecond} {
		t.Run(invalidTimeout.String(), func(t *testing.T) {
			var remaining time.Duration
			double := &mongoClientDouble{
				ping: func(ctx context.Context) error {
					deadline, ok := ctx.Deadline()
					if !ok {
						return errors.New("mongodb readiness context has no deadline")
					}
					remaining = time.Until(deadline)
					return ctx.Err()
				},
			}
			assembly := mongoTestAssembly(func(context.Context, rtmongo.ConnectConfig) (rtmongo.Handle, error) {
				return double, nil
			})

			if _, err := assembly.MongoWithReadinessTimeout(MongoConfig{
				URI: "mongodb://db:27017", Database: "quwoquan_tag",
			}, invalidTimeout); err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			result := assembly.Health.Check(context.Background())

			if result.Status != "ok" || len(result.Checks) != 1 || result.Checks["mongodb"] != "ok" {
				t.Fatalf("invalid timeout must use the default mongodb check budget, got %+v", result)
			}
			if remaining < time.Second || remaining > 3*time.Second {
				t.Fatalf("invalid timeout did not fall back to the default readiness budget: %v", remaining)
			}
		})
	}
}

// 第二条 Mongo 连接（如跨服务只读 fence 库）必须以独立检查名登记；复用 "mongodb"
// 会被 health registry 记为永久失败，服务永远不 ready（alpha 冷启动实测）。
func TestAssemblyMongoNamedRegistersDistinctHealthCheckBesidePrimary(t *testing.T) {
	primary := &mongoClientDouble{}
	fence := &mongoClientDouble{}
	calls := 0
	assembly := mongoTestAssembly(func(_ context.Context, cfg rtmongo.ConnectConfig) (rtmongo.Handle, error) {
		calls++
		if strings.Contains(cfg.URI, "content") {
			return fence, nil
		}
		return primary, nil
	})

	if _, err := assembly.Mongo(MongoConfig{URI: "mongodb://user:27017", Database: "quwoquan_user"}); err != nil {
		t.Fatalf("primary mongo: %v", err)
	}
	if _, err := assembly.MongoNamed("content_release_fence_mongodb", MongoConfig{
		URI: "mongodb://content:27017", Database: "quwoquan_content",
	}); err != nil {
		t.Fatalf("named mongo: %v", err)
	}
	if calls != 2 {
		t.Fatalf("expected two connections, got %d", calls)
	}

	result := assembly.Health.Check(context.Background())
	if result.Status != "ok" {
		t.Fatalf("two distinct mongo checks must both pass, got %v", result.Checks)
	}
	for _, name := range []string{"mongodb", "content_release_fence_mongodb"} {
		if _, registered := result.Checks[name]; !registered {
			t.Fatalf("expected %s health check registration, got %v", name, result.Checks)
		}
	}
	if primary.pings == 0 || fence.pings == 0 {
		t.Fatalf("both clients must be pinged: primary=%d fence=%d", primary.pings, fence.pings)
	}

	if _, err := assembly.MongoNamed("mongodb", MongoConfig{URI: "mongodb://x:27017", Database: "x"}); err == nil {
		t.Fatal("MongoNamed must refuse the primary check name")
	}
	if _, err := assembly.MongoNamed(" ", MongoConfig{URI: "mongodb://x:27017", Database: "x"}); err == nil {
		t.Fatal("MongoNamed must refuse an empty check name")
	}
}
