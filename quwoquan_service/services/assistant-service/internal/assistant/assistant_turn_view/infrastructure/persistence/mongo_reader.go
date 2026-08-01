package persistence

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
)

var terminalStatuses = []string{"completed", "failed", "cancelled"}

type MongoReader struct {
	sessions *mongo.Collection
	runs     *mongo.Collection
}

func NewMongoReader(database *mongo.Database) *MongoReader {
	if database == nil {
		panic("assistant turn view Mongo database is required")
	}
	return &MongoReader{
		sessions: database.Collection("assistant_sessions"),
		runs:     database.Collection("assistant_runs"),
	}
}

type terminalTurnDocument struct {
	TurnID    string `bson:"_id"`
	SessionID string `bson:"sessionId"`
	Status    string `bson:"status"`
	Input     struct {
		Text string `bson:"text"`
	} `bson:"input"`
	TerminalSnapshot *assistant.AssistantRunTerminalSnapshot `bson:"terminalSnapshot,omitempty"`
	SkillID          string                                  `bson:"skillId,omitempty"`
	DomainID         string                                  `bson:"domainId,omitempty"`
	CreatedAt        time.Time                               `bson:"createdAt"`
	CompletedAt      *time.Time                              `bson:"completedAt,omitempty"`
}

func (reader *MongoReader) ListSessionTurns(
	ctx context.Context,
	userID string,
	sessionID string,
	limit int,
	cursor string,
) (turnviewmodel.AssistantTurnListView, error) {
	if reader == nil || reader.sessions == nil || reader.runs == nil {
		return turnviewmodel.AssistantTurnListView{},
			errors.New("assistant turn view Mongo reader is not configured")
	}
	if err := reader.sessions.FindOne(
		ctx,
		bson.M{"_id": sessionID, "userId": userID},
		options.FindOne().SetProjection(bson.M{"_id": 1}),
	).Err(); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return turnviewmodel.AssistantTurnListView{},
				turnviewmodel.ErrSessionNotFound
		}
		return turnviewmodel.AssistantTurnListView{}, err
	}

	filter := bson.M{
		"sessionId": sessionID,
		"userId":    userID,
		"status":    bson.M{"$in": terminalStatuses},
	}
	if cursor != "" {
		createdAt, turnID, ok := decodeCursor(cursor)
		if !ok {
			return turnviewmodel.AssistantTurnListView{}, turnviewmodel.ErrInvalidCursor
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": createdAt}},
			bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": turnID}},
		}
	}

	findCursor, err := reader.runs.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return turnviewmodel.AssistantTurnListView{}, err
	}
	defer findCursor.Close(ctx)

	documents := []terminalTurnDocument{}
	if err := findCursor.All(ctx, &documents); err != nil {
		return turnviewmodel.AssistantTurnListView{}, err
	}
	nextCursor := ""
	if len(documents) > limit {
		documents = documents[:limit]
		last := documents[len(documents)-1]
		nextCursor = encodeCursor(last.CreatedAt, last.TurnID)
	}
	items := make([]turnviewmodel.AssistantTurnSummaryView, 0, len(documents))
	for _, document := range documents {
		completedAt := ""
		if document.CompletedAt != nil {
			completedAt = document.CompletedAt.UTC().Format(time.RFC3339)
		}
		items = append(items, turnviewmodel.AssistantTurnSummaryView{
			TurnID:           document.TurnID,
			SessionID:        document.SessionID,
			Status:           document.Status,
			InputText:        document.Input.Text,
			TerminalSnapshot: document.TerminalSnapshot,
			SkillID:          document.SkillID,
			DomainID:         document.DomainID,
			CreatedAt:        document.CreatedAt.UTC().Format(time.RFC3339),
			CompletedAt:      completedAt,
		})
	}
	return turnviewmodel.AssistantTurnListView{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}

func encodeCursor(createdAt time.Time, turnID string) string {
	value := fmt.Sprintf("%d|%s", createdAt.UTC().UnixNano(), turnID)
	return base64.RawURLEncoding.EncodeToString([]byte(value))
}

func decodeCursor(cursor string) (time.Time, string, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(cursor))
	if err != nil {
		return time.Time{}, "", false
	}
	parts := strings.SplitN(string(raw), "|", 2)
	if len(parts) != 2 || strings.TrimSpace(parts[1]) == "" {
		return time.Time{}, "", false
	}
	nanos, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		return time.Time{}, "", false
	}
	return time.Unix(0, nanos).UTC(), parts[1], true
}
