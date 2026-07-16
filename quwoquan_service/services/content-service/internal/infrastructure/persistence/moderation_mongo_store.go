package persistence

import (
	"go.mongodb.org/mongo-driver/v2/mongo"
)

// MongoPostModerationCaseStore is the sole production adapter for independent
// PostModerationCase state, reviewer audit, durable receipts, and its outbox.
// It has no process-memory fallback.
type MongoPostModerationCaseStore struct {
	cases    *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
	audit    *mongo.Collection
}

func NewMongoPostModerationCaseStore(
	cases *mongo.Collection,
) *MongoPostModerationCaseStore {
	if cases == nil {
		panic("NewMongoPostModerationCaseStore requires post_moderation_cases collection")
	}
	db := cases.Database()
	return &MongoPostModerationCaseStore{
		cases:    cases,
		receipts: db.Collection("post_moderation_case_command_receipts"),
		outbox:   db.Collection("post_moderation_case_outbox"),
		audit:    db.Collection("post_moderation_case_audit"),
	}
}
