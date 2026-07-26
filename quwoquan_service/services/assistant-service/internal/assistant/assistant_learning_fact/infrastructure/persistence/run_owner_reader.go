package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
)

type MongoRunOwnerReader struct {
	runs *mongo.Collection
}

func NewMongoRunOwnerReader(database *mongo.Database) *MongoRunOwnerReader {
	if database == nil {
		return &MongoRunOwnerReader{}
	}
	return &MongoRunOwnerReader{
		runs: database.Collection("assistant_runs"),
	}
}

func (reader *MongoRunOwnerReader) ResolveRunOwner(
	ctx context.Context,
	runID string,
) (learningapplication.RunOwner, bool, error) {
	if reader == nil || reader.runs == nil {
		return learningapplication.RunOwner{}, false,
			learningapplication.ErrStoreUnavailable
	}
	var document struct {
		UserID         string `bson:"userId"`
		RequestContext struct {
			PersonaID string `bson:"personaId"`
		} `bson:"requestContext"`
		Trigger struct {
			MessageID string `bson:"messageId"`
		} `bson:"trigger"`
	}
	err := reader.runs.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(runID)},
		options.FindOne().SetProjection(bson.M{
			"userId":                   1,
			"requestContext.personaId": 1,
			"trigger.messageId":        1,
		}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return learningapplication.RunOwner{}, false, nil
	}
	if err != nil {
		return learningapplication.RunOwner{}, false, fmt.Errorf(
			"read assistant run owner: %w",
			err,
		)
	}
	return learningapplication.RunOwner{
		UserID:           strings.TrimSpace(document.UserID),
		PersonaID:        strings.TrimSpace(document.RequestContext.PersonaID),
		TriggerMessageID: strings.TrimSpace(document.Trigger.MessageID),
	}, true, nil
}
