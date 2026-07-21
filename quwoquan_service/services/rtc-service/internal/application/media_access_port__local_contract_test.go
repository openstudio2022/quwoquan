package application

import (
	"context"
	"errors"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/internal/generated"
)

func TestMediaAccessPortReturnsTypedAccessAndHidesProviderFailure(t *testing.T) {
	provider := &mediaAccessPortFake{
		access: MediaSessionAccess{
			AccessToken: "opaque-access-token",
		},
	}
	orchestrator := &CallOrchestrator{mediaProvider: provider}

	access, err := orchestrator.issueMediaAccess(
		context.Background(),
		"room-1",
		"persona-1",
	)
	if err != nil {
		t.Fatalf("issueMediaAccess() error = %v", err)
	}
	if access.AccessToken != provider.access.AccessToken {
		t.Fatalf("typed media access = %#v", access)
	}

	provider.err = errors.New("livekit upstream diagnostic")
	_, err = orchestrator.issueMediaAccess(context.Background(), "room-1", "persona-1")
	if err == nil {
		t.Fatal("provider failure must be mapped to a structured RTC error")
	}
	if got := rterr.NormalizeError(err).Code.String(); got != generated.ErrMediaTransportUnavailable.Error() {
		t.Fatalf("error code = %s, want %s", got, generated.ErrMediaTransportUnavailable.Error())
	}
	if strings.Contains(strings.ToLower(err.Error()), "livekit") {
		t.Fatalf("provider identity leaked through application error: %v", err)
	}
}

type mediaAccessPortFake struct {
	access MediaSessionAccess
	err    error
}

func (*mediaAccessPortFake) CreateRoom(context.Context, string, int) error { return nil }

func (*mediaAccessPortFake) DeleteRoom(context.Context, string) error { return nil }

func (*mediaAccessPortFake) ListParticipants(
	context.Context,
	string,
) ([]RoomParticipant, error) {
	return nil, nil
}

func (*mediaAccessPortFake) RemoveParticipant(context.Context, string, string) error {
	return nil
}

func (f *mediaAccessPortFake) IssueParticipantAccess(
	context.Context,
	string,
	string,
) (MediaSessionAccess, error) {
	if f.err != nil {
		return MediaSessionAccess{}, f.err
	}
	return f.access, nil
}
