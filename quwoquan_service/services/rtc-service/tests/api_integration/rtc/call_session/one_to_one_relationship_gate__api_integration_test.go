// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/generated/rtc/call_session"
	rtchttp "quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/http"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application/commandmeta"
	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	rtccache "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/persistence"
)

func newGateTestOrchestrator(t *testing.T, gate application.RelationshipGate) *application.CallOrchestrator {
	t.Helper()
	callStore := persistence.NewMongoCallStore(requireMongoDB(t))
	callCache := rtccache.NewCallStateCache(redisRouter.Scene("general"))
	domainSvc := callsession.NewCallSessionService()
	return application.NewCallOrchestrator(
		callStore,
		callCache,
		domainSvc,
		newTestMediaRoomProvider(),
		gate,
		application.WithCallAccountSecurityGate(
			application.AllowCallAccountSecurityForTest(),
		),
	)
}

func rtcRelationshipGateForContractTest(
	t *testing.T,
	capability application.RelationshipCapability,
) application.RelationshipGate {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || strings.TrimSpace(r.Header.Get("X-Client-User-Id")) == "" {
			http.Error(w, "invalid relationship capability request", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{
			"isMutual":    capability.IsMutual,
			"isBlocked":   capability.IsBlocked,
			"isBlockedBy": capability.IsBlockedBy,
		})
	}))
	t.Cleanup(server.Close)
	return rtchttp.NewUserRelationshipGate(server.URL, server.Client())
}

func TestInitiateCall_OneToOne_RequiresMutual(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	orchestrator := newGateTestOrchestrator(
		t,
		rtcRelationshipGateForContractTest(t, application.RelationshipCapability{}),
	)

	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		"gate-reject-not-mutual",
	)
	_, err := orchestrator.InitiateCall(ctx, application.InitiateCallRequest{
		InitiatorID: "caller_a",
		CallType:    "audio",
		InviteeIDs:  []string{"caller_b"},
	})
	if err == nil {
		t.Fatal("expected not mutual gate error")
	}
	if got := rterr.NormalizeError(err).Code.String(); got != generated.ErrNotMutual.Error() {
		t.Fatalf("expected %s, got %s", generated.ErrNotMutual.Error(), got)
	}
}

func TestInitiateCall_OneToOne_Blocked(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	orchestrator := newGateTestOrchestrator(
		t,
		rtcRelationshipGateForContractTest(
			t,
			application.RelationshipCapability{IsBlocked: true},
		),
	)

	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		"gate-reject-blocked",
	)
	_, err := orchestrator.InitiateCall(ctx, application.InitiateCallRequest{
		InitiatorID: "caller_c",
		CallType:    "audio",
		InviteeIDs:  []string{"caller_d"},
	})
	if err == nil {
		t.Fatal("expected blocked gate error")
	}
	if got := rterr.NormalizeError(err).Code.String(); got != generated.ErrBlocked.Error() {
		t.Fatalf("expected %s, got %s", generated.ErrBlocked.Error(), got)
	}
}

func TestInitiateCall_OneToOne_AllowsMutual(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	orchestrator := newGateTestOrchestrator(
		t,
		rtcRelationshipGateForContractTest(
			t,
			application.RelationshipCapability{IsMutual: true},
		),
	)

	ctx := commandmeta.WithIdempotencyKey(context.Background(), "gate-allow-mutual")
	resp, err := orchestrator.InitiateCall(ctx, application.InitiateCallRequest{
		InitiatorID: "caller_ok",
		CallType:    "audio",
		InviteeIDs:  []string{"peer_ok"},
	})
	if err != nil {
		t.Fatalf("initiate call: %v", err)
	}
	if resp == nil || resp.Session == nil || resp.Session.ID == "" {
		t.Fatal("expected call session")
	}
}
