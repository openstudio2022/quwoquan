package tests

import (
	"context"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	"quwoquan_service/services/rtc-service/internal/generated"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

type rtcStubRelationshipGate struct {
	cap application.RelationshipCapability
	err error
}

func (g rtcStubRelationshipGate) GetCapability(context.Context, string, string) (application.RelationshipCapability, error) {
	return g.cap, g.err
}

func newGateTestOrchestrator(t *testing.T, gate application.RelationshipGate) *application.CallOrchestrator {
	t.Helper()
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	callStore := persistence.NewMongoCallStore(mongoDB)
	callCache := rtccache.NewCallStateCache(redisRouter.Scene("general"))
	domainSvc := callsession.NewCallSessionService()
	tokenSvc := application.NewTokenService("testkey", "testsecret")
	return application.NewCallOrchestrator(callStore, callCache, domainSvc, nil, tokenSvc, nil, gate)
}

func TestInitiateCall_OneToOne_RequiresMutual(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	orchestrator := newGateTestOrchestrator(t, rtcStubRelationshipGate{})

	_, err := orchestrator.InitiateCall(context.Background(), application.InitiateCallRequest{
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
	orchestrator := newGateTestOrchestrator(t, rtcStubRelationshipGate{
		cap: application.RelationshipCapability{IsBlocked: true},
	})

	_, err := orchestrator.InitiateCall(context.Background(), application.InitiateCallRequest{
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
	orchestrator := newGateTestOrchestrator(t, rtcStubRelationshipGate{
		cap: application.RelationshipCapability{IsMutual: true},
	})

	resp, err := orchestrator.InitiateCall(context.Background(), application.InitiateCallRequest{
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
