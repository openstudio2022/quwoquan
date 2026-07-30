package local_contract

import (
	"testing"

	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

func TestMessageCardKindIsClosedSnakeCaseWireSet(t *testing.T) {
	t.Parallel()

	canonical := []messagemodel.MessageCardKind{
		messagemodel.MessageCardKindProfileQR,
		messagemodel.MessageCardKindContentPost,
		messagemodel.MessageCardKindUserProfile,
		messagemodel.MessageCardKindEntityProfile,
		messagemodel.MessageCardKindCircle,
		messagemodel.MessageCardKindRTCCallLog,
	}
	for _, kind := range canonical {
		if !kind.Valid() {
			t.Fatalf("canonical MessageCardKind %q must be valid", kind)
		}
	}

	for _, legacy := range []messagemodel.MessageCardKind{
		"profileQr", "post", "userProfile", "entityProfile",
	} {
		if legacy.Valid() {
			t.Fatalf("legacy MessageCardKind %q must be rejected", legacy)
		}
	}
}
