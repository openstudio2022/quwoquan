package persistence_test

import (
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	persistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

// storage_ref: services/circle-service/contracts/circle_management/gathering/storage.yaml#collections.gatherings
func TestScopeAStoreOmitsUnboundConversationFromSparseUniqueIndex(t *testing.T) {
	value := model.Gathering{
		ID:                "gathering-pending",
		Version:           1,
		LifecycleStatus:   contract.GatheringLifecycleStatusDraft,
		RoomBindingStatus: contract.GatheringRoomBindingStatusPending,
		CreatedAt:         time.Now().UTC(),
		UpdatedAt:         time.Now().UTC(),
	}
	document, err := persistence.EncodeGatheringDocument(value)
	if err != nil {
		t.Fatalf("encode pending Gathering: %v", err)
	}
	if _, exists := document["conversationId"]; exists {
		t.Fatalf("pending draft must omit conversationId: %+v", document)
	}
	for _, field := range []string{
		"organizerAssignments",
		"participations",
		"revisions",
		"availabilityWatches",
	} {
		if _, ok := document[field].(bson.A); !ok {
			t.Fatalf("%s must encode as a non-null BSON array: %#v", field, document[field])
		}
	}

	value.ConversationID = "conversation-canonical"
	value.RoomBindingStatus = contract.GatheringRoomBindingStatusReady
	document, err = persistence.EncodeGatheringDocument(value)
	if err != nil {
		t.Fatalf("encode ready Gathering: %v", err)
	}
	if got := document["conversationId"]; got != value.ConversationID {
		t.Fatalf("ready conversationId = %#v", got)
	}
}

// storage_ref: services/circle-service/contracts/circle_management/gathering/storage.yaml#indexes
func TestScopeAStoreIdentifiesDuplicateByIndexName(t *testing.T) {
	conversationDuplicate := mongo.WriteException{
		WriteErrors: []mongo.WriteError{{
			Code:    11000,
			Message: "E11000 duplicate key error collection: circle.gatherings index: uq_gathering_conversation dup key",
		}},
	}
	if got := persistence.DuplicateIndexName(conversationDuplicate); got != "uq_gathering_conversation" {
		t.Fatalf("conversation duplicate index = %q", got)
	}

	idDuplicate := mongo.WriteException{
		WriteErrors: []mongo.WriteError{{
			Code:    11000,
			Message: "E11000 duplicate key error collection: circle.gathering_command_receipts index: _id_ dup key",
		}},
	}
	if got := persistence.DuplicateIndexName(idDuplicate); got != "_id_" {
		t.Fatalf("receipt duplicate index = %q", got)
	}

	unknownDuplicate := mongo.WriteException{
		WriteErrors: []mongo.WriteError{{
			Code:    11000,
			Message: "E11000 duplicate key error collection: circle.gatherings index: unknown_unique dup key",
		}},
	}
	if got := persistence.DuplicateIndexName(unknownDuplicate); got != "" {
		t.Fatalf("unknown duplicate must not be misclassified: %q", got)
	}
}
