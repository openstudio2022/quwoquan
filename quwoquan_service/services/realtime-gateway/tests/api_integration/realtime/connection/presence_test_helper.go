package api_integration

import (
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	connectionpresence "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/connection"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"
)

func newIntegrationPresenceProjection(
	t *testing.T,
	client rtredis.Client,
) *connectionpresence.Projector {
	t.Helper()
	store, err := presenceredis.NewStore(client)
	if err != nil {
		t.Fatal(err)
	}
	projector, err := presenceapp.NewProjector(store)
	if err != nil {
		t.Fatal(err)
	}
	revoker, err := presenceapp.NewRevoker(store)
	if err != nil {
		t.Fatal(err)
	}
	adapter, err := connectionpresence.NewProjector(projector, revoker)
	if err != nil {
		t.Fatal(err)
	}
	return adapter
}
