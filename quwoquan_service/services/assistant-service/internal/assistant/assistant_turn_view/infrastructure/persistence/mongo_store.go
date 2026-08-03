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

	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
)

const terminalProjectionCheckpointID = "assistant_run_terminal_projection"

type checkpointDocument struct {
	ID              string    `bson:"_id"`
	SourceUpdatedAt time.Time `bson:"sourceUpdatedAt"`
	SourceRunID     string    `bson:"sourceRunId"`
}

type MongoStore struct {
	views       *mongo.Collection
	checkpoints *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("assistant turn view Mongo database is required")
	}
	return &MongoStore{
		views:       database.Collection("assistant_turn_views"),
		checkpoints: database.Collection("assistant_turn_view_checkpoints"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.views.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "sessionId", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_turn_views_owner_session_created"),
		},
		{
			Keys:    bson.D{{Key: "sourceUpdatedAt", Value: 1}},
			Options: options.Index().SetName("idx_turn_views_source_updated"),
		},
	})
	if err != nil {
		return fmt.Errorf("create assistant turn view indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) LoadCheckpoint(
	ctx context.Context,
) (turnviewmodel.Checkpoint, error) {
	var document checkpointDocument
	err := store.checkpoints.FindOne(
		ctx,
		bson.M{"_id": terminalProjectionCheckpointID},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return turnviewmodel.Checkpoint{}, nil
	}
	if err != nil {
		return turnviewmodel.Checkpoint{}, fmt.Errorf("load assistant turn view checkpoint: %w", err)
	}
	return turnviewmodel.Checkpoint{
		SourceUpdatedAt: document.SourceUpdatedAt.UTC(),
		SourceRunID:     document.SourceRunID,
	}, nil
}

// Apply advances one idempotent projection and its source checkpoint in the
// same transaction. A checkpoint can therefore never move past a missing view.
func (store *MongoStore) Apply(
	ctx context.Context,
	projection turnviewmodel.Projection,
	checkpoint turnviewmodel.Checkpoint,
) error {
	session, err := store.views.Database().Client().StartSession()
	if err != nil {
		return fmt.Errorf("start assistant turn view transaction: %w", err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if _, err := store.views.ReplaceOne(
			txCtx,
			bson.M{"_id": projection.TurnID},
			projection,
			options.Replace().SetUpsert(true),
		); err != nil {
			return nil, fmt.Errorf("upsert assistant turn view: %w", err)
		}
		if _, err := store.checkpoints.ReplaceOne(
			txCtx,
			bson.M{"_id": terminalProjectionCheckpointID},
			checkpointDocument{
				ID:              terminalProjectionCheckpointID,
				SourceUpdatedAt: checkpoint.SourceUpdatedAt.UTC(),
				SourceRunID:     checkpoint.SourceRunID,
			},
			options.Replace().SetUpsert(true),
		); err != nil {
			return nil, fmt.Errorf("advance assistant turn view checkpoint: %w", err)
		}
		return nil, nil
	})
	if err != nil {
		return fmt.Errorf("commit assistant turn view projection: %w", err)
	}
	return nil
}

func (store *MongoStore) ListSessionTurns(
	ctx context.Context,
	userID string,
	sessionID string,
	limit int,
	cursor string,
) (turnviewmodel.AssistantTurnListView, error) {
	if store == nil || store.views == nil {
		return turnviewmodel.AssistantTurnListView{},
			errors.New("assistant turn view Mongo store is not configured")
	}
	filter := bson.M{
		"sessionId": strings.TrimSpace(sessionID),
		"userId":    strings.TrimSpace(userID),
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

	findCursor, err := store.views.Find(
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
	projections := []turnviewmodel.Projection{}
	if err := findCursor.All(ctx, &projections); err != nil {
		return turnviewmodel.AssistantTurnListView{}, err
	}
	nextCursor := ""
	if len(projections) > limit {
		projections = projections[:limit]
		last := projections[len(projections)-1]
		nextCursor = encodeCursor(last.CreatedAt, last.TurnID)
	}
	items := make([]turnviewmodel.AssistantTurnSummaryView, 0, len(projections))
	for _, projection := range projections {
		completedAt := ""
		if projection.CompletedAt != nil {
			completedAt = projection.CompletedAt.UTC().Format(time.RFC3339)
		}
		items = append(items, turnviewmodel.AssistantTurnSummaryView{
			TurnID:           projection.TurnID,
			SessionID:        projection.SessionID,
			Status:           projection.Status,
			InputText:        projection.InputText,
			TerminalSnapshot: projection.TerminalSnapshot,
			SkillID:          projection.SkillID,
			DomainID:         projection.DomainID,
			CreatedAt:        projection.CreatedAt.UTC().Format(time.RFC3339),
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
