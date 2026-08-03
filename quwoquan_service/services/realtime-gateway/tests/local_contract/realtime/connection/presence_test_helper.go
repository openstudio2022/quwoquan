package local_contract

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	connectionpresence "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/connection"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"
)

func newTestPresenceProjection(
	t *testing.T,
	client rtredis.Client,
) *connectionpresence.Projector {
	t.Helper()
	store, err := presenceredis.NewStore(client)
	if err != nil {
		t.Fatalf("new presence store: %v", err)
	}
	projector, err := presenceapp.NewProjector(store)
	if err != nil {
		t.Fatalf("new presence projector: %v", err)
	}
	revoker, err := presenceapp.NewRevoker(store)
	if err != nil {
		t.Fatalf("new presence revoker: %v", err)
	}
	adapter, err := connectionpresence.NewProjector(projector, revoker)
	if err != nil {
		t.Fatalf("new presence connection adapter: %v", err)
	}
	return adapter
}
