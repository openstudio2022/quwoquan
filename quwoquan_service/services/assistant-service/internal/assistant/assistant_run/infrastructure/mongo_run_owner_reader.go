package infrastructure

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

type MongoRunOwnerReader struct {
	runs *mongo.Collection
}

func NewMongoRunOwnerReader(database *mongo.Database) *MongoRunOwnerReader {
	if database == nil {
		return &MongoRunOwnerReader{}
	}
	return &MongoRunOwnerReader{runs: database.Collection("assistant_runs")}
}

func (reader *MongoRunOwnerReader) ResolveRunOwner(
	ctx context.Context,
	runID string,
) (rundomain.Owner, bool, error) {
	if reader == nil || reader.runs == nil {
		return rundomain.Owner{}, false, errors.New("assistant run store unavailable")
	}
	var document struct {
		UserID    string `bson:"userId"`
		PersonaID string `bson:"personaId"`
		Snapshot  struct {
			Trigger map[string]any `bson:"trigger"`
		} `bson:"snapshot"`
	}
	err := reader.runs.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(runID)},
		options.FindOne().SetProjection(bson.M{
			"userId":           1,
			"personaId":        1,
			"snapshot.trigger": 1,
		}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return rundomain.Owner{}, false, nil
	}
	if err != nil {
		return rundomain.Owner{}, false, fmt.Errorf("read assistant run owner: %w", err)
	}
	triggerMessageID, _ := document.Snapshot.Trigger["messageId"].(string)
	return rundomain.Owner{
		UserID:           strings.TrimSpace(document.UserID),
		PersonaID:        strings.TrimSpace(document.PersonaID),
		TriggerMessageID: strings.TrimSpace(triggerMessageID),
	}, true, nil
}
