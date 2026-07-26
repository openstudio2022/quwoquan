package local_contract

import (
	"testing"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func TestProductionDependenciesUseTypedPorts(t *testing.T) {
	if application.DenyRelationshipGate() == nil {
		t.Fatal("conversation composition requires a typed relationship gate")
	}
}
