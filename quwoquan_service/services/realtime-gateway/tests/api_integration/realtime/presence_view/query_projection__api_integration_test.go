// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	presencehttp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/http"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/domain/model"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"
)

func TestPresenceViewRealRedisProjectionAndNamedReader(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("presence api_integration requires real Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancelCleanup()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush Redis: %v", err)
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": {
				Mode:     "standalone",
				Addr:     realRedis.Addr,
				Password: realRedis.Password,
				DB:       0,
				TLS:      realRedis.TLS,
			},
		},
		DefaultScene: "realtime",
	})
	if err != nil {
		t.Fatalf("new Redis router: %v", err)
	}
	t.Cleanup(func() { _ = router.Close() })
	store, err := presenceredis.NewStore(router.Scene("realtime"))
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	newer, err := model.NewDevice(
		"account-presence-api",
		"persona-presence-api",
		"device-presence-api",
		"connection-new",
		"node-new",
		"websocket",
		now,
		2,
	)
	if err != nil {
		t.Fatal(err)
	}
	if written, err := store.UpsertIfNewer(ctx, newer); err != nil || !written {
		t.Fatalf("write newer presence: written=%v err=%v", written, err)
	}
	older := newer
	older.ConnectionID = "connection-old"
	older.NodeID = "node-old"
	older.Sequence = 1
	older.LastHeartbeatAt = now.Add(time.Second)
	older.ExpiresAt = older.LastHeartbeatAt.Add(model.ProjectionTTL)
	if written, err := store.UpsertIfNewer(ctx, older); err != nil || written {
		t.Fatalf("older fence overwrote projection: written=%v err=%v", written, err)
	}
	queries, err := presenceapp.NewQueryFacade(store)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	presencehttp.NewHandler(queries).Routes(mux)
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)
	response, err := server.Client().Get(
		server.URL + "/internal/realtime/personas/persona-presence-api/presence",
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("presence named reader status=%d", response.StatusCode)
	}
	var body model.View
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body.Devices) != 1 ||
		body.Devices[0].ConnectionID != newer.ConnectionID ||
		body.Devices[0].Sequence != newer.Sequence {
		t.Fatalf("presence body=%+v", body)
	}
}
