package persistence

import (
	"context"
	"errors"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func (store *MongoChatStore) LoadCircleGroupMembershipProjection(
	ctx context.Context,
	circleGroupID string,
	userID string,
) (application.CircleGroupMembershipProjectionState, bool, error) {
	var document circleGroupMembershipProjectionDocument
	err := store.circleGroupProjections.FindOne(ctx, bson.M{
		"circleGroupId": circleGroupID,
		"userId":        userID,
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.CircleGroupMembershipProjectionState{}, false, nil
	}
	if err != nil {
		return application.CircleGroupMembershipProjectionState{}, false, err
	}
	return document.toApplication(), true, nil
}

func (store *MongoChatStore) SaveCircleGroupMembershipProjection(
	ctx context.Context,
	state application.CircleGroupMembershipProjectionState,
) error {
	document := circleGroupMembershipProjectionDocument{
		CircleGroupID:  state.CircleGroupID,
		ConversationID: state.ConversationID,
		UserID:         state.UserID,
		SourceVersion:  state.SourceVersion,
		State:          state.State,
		Role:           state.Role,
		LastEventID:    state.LastEventID,
		UpdatedAt:      state.UpdatedAt.UTC(),
	}
	_, err := store.circleGroupProjections.ReplaceOne(
		ctx,
		bson.M{"circleGroupId": document.CircleGroupID, "userId": document.UserID},
		document,
		options.Replace().SetUpsert(true),
	)
	return err
}

type circleGroupMembershipProjectionDocument struct {
	CircleGroupID  string    `bson:"circleGroupId"`
	ConversationID string    `bson:"conversationId"`
	UserID         string    `bson:"userId"`
	SourceVersion  int64     `bson:"sourceVersion"`
	State          string    `bson:"state"`
	Role           string    `bson:"role"`
	LastEventID    string    `bson:"lastEventId"`
	UpdatedAt      time.Time `bson:"updatedAt"`
}

func (document circleGroupMembershipProjectionDocument) toApplication() application.CircleGroupMembershipProjectionState {
	return application.CircleGroupMembershipProjectionState{
		CircleGroupID:  document.CircleGroupID,
		ConversationID: document.ConversationID,
		UserID:         document.UserID,
		SourceVersion:  document.SourceVersion,
		State:          document.State,
		Role:           document.Role,
		LastEventID:    document.LastEventID,
		UpdatedAt:      document.UpdatedAt.UTC(),
	}
}
