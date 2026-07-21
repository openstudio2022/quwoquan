package persistence

import (
	"context"
	"errors"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/application"
)

func (s *MongoChatStore) LoadCircleGroupChatBindingProjection(
	ctx context.Context,
	circleGroupID string,
) (application.CircleGroupChatBindingProjectionState, bool, error) {
	var document circleGroupChatBindingProjectionDocument
	err := s.circleGroupBindingProjections.FindOne(
		ctx,
		bson.M{"circleGroupId": circleGroupID},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.CircleGroupChatBindingProjectionState{}, false, nil
	}
	if err != nil {
		return application.CircleGroupChatBindingProjectionState{}, false, err
	}
	return document.toApplication(), true, nil
}

func (s *MongoChatStore) SaveCircleGroupChatBindingProjection(
	ctx context.Context,
	state application.CircleGroupChatBindingProjectionState,
) error {
	document := circleGroupChatBindingProjectionDocument{
		CircleGroupID: state.CircleGroupID,
		CircleID:      state.CircleID,
		SourceVersion: state.SourceVersion,
		Status:        state.Status,
		LastEventID:   state.LastEventID,
		UpdatedAt:     state.UpdatedAt.UTC(),
	}
	_, err := s.circleGroupBindingProjections.ReplaceOne(
		ctx,
		bson.M{"circleGroupId": document.CircleGroupID},
		document,
		options.Replace().SetUpsert(true),
	)
	return err
}

type circleGroupChatBindingProjectionDocument struct {
	CircleGroupID string    `bson:"circleGroupId"`
	CircleID      string    `bson:"circleId"`
	SourceVersion int64     `bson:"sourceVersion"`
	Status        string    `bson:"status"`
	LastEventID   string    `bson:"lastEventId"`
	UpdatedAt     time.Time `bson:"updatedAt"`
}

func (document circleGroupChatBindingProjectionDocument) toApplication() application.CircleGroupChatBindingProjectionState {
	return application.CircleGroupChatBindingProjectionState{
		CircleGroupID: document.CircleGroupID,
		CircleID:      document.CircleID,
		SourceVersion: document.SourceVersion,
		Status:        document.Status,
		LastEventID:   document.LastEventID,
		UpdatedAt:     document.UpdatedAt.UTC(),
	}
}
