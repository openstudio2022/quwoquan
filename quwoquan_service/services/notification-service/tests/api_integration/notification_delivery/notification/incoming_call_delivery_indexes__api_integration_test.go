// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#req-010
package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestIncomingCallDeliveryJobsInstallExternalInteractionUniquenessIndexes(t *testing.T) {
	t.Helper()
	cursor, err := notificationMongoDB.Collection("notification_delivery_jobs").Indexes().List(
		context.Background(),
	)
	if err != nil {
		t.Fatalf("list incoming call delivery indexes: %v", err)
	}
	defer cursor.Close(context.Background())

	found := map[string]bool{}
	for cursor.Next(context.Background()) {
		var index bson.M
		if err := cursor.Decode(&index); err != nil {
			t.Fatalf("decode incoming call delivery index: %v", err)
		}
		name, _ := index["name"].(string)
		if name == "uq_notification_incoming_call_external_interaction" ||
			name == "uq_notification_incoming_call_cancellation_external_interaction" {
			unique, _ := index["unique"].(bool)
			found[name] = unique
		}
	}
	if err := cursor.Err(); err != nil {
		t.Fatalf("iterate incoming call delivery indexes: %v", err)
	}
	for _, name := range []string{
		"uq_notification_incoming_call_external_interaction",
		"uq_notification_incoming_call_cancellation_external_interaction",
	} {
		if !found[name] {
			t.Fatalf("required unique external interaction index is missing: %s", name)
		}
	}
}
