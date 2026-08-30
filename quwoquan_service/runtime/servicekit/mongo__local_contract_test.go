package servicekit

import (
	"context"
	"errors"
	"strings"
	"testing"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rthealth "quwoquan_service/runtime/health"
)

// mongoClientDouble 是窄投影的同包 typed double：只验证编排（连接、健康
// 检查、清理注册），不触真实 Mongo；double 不出测试树。
type mongoClientDouble struct {
	pings       int
	disconnects int
	pingErr     error
}

func (double *mongoClientDouble) Ping(context.Context) error {
	double.pings++
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
