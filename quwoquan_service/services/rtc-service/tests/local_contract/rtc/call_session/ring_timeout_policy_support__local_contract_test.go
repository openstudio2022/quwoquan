package local_contract

import (
	"testing"
	"time"

	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
)

func newTestCallSessionService(
	tb testing.TB,
	oneToOne time.Duration,
	group time.Duration,
) *callsession.CallSessionService {
	tb.Helper()
	policy, err := callsession.NewRingTimeoutPolicy(oneToOne, group)
	if err != nil {
		tb.Fatalf("NewRingTimeoutPolicy() error = %v", err)
	}
	service, err := callsession.NewCallSessionService(policy)
	if err != nil {
		tb.Fatalf("NewCallSessionService() error = %v", err)
	}
	return service
}
