package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

type MongoGatheringPlanReader struct {
	plans *mongo.Collection
}

func NewMongoGatheringPlanReader(database *mongo.Database) *MongoGatheringPlanReader {
	if database == nil {
		panic("GatheringPlan Reader requires database")
	}
	return &MongoGatheringPlanReader{plans: database.Collection(planCollection)}
}

func (reader *MongoGatheringPlanReader) ReadByGathering(ctx context.Context, gatheringID string) (model.GatheringPlan, bool, error) {
	return reader.readOne(ctx, bson.M{"gatheringId": strings.TrimSpace(gatheringID)})
}

func (reader *MongoGatheringPlanReader) ReadByID(ctx context.Context, planID string) (model.GatheringPlan, bool, error) {
	return reader.readOne(ctx, bson.M{"_id": strings.TrimSpace(planID)})
}

func (reader *MongoGatheringPlanReader) readOne(ctx context.Context, filter bson.M) (model.GatheringPlan, bool, error) {
	var value model.GatheringPlan
	err := reader.plans.FindOne(ctx, filter).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.GatheringPlan{}, false, nil
	}
	if err != nil {
		return model.GatheringPlan{}, false, err
	}
	if err := value.Validate(); err != nil {
		return model.GatheringPlan{}, false, err
	}
	return value, true, nil
}

func (reader *MongoGatheringPlanReader) ListRevisions(ctx context.Context, planID, cursor string, limit int) (model.RevisionPage, error) {
	planID = strings.TrimSpace(planID)
	if planID == "" {
		return model.RevisionPage{}, model.ErrInvalid
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	after, err := decodeRevisionCursor(planID, strings.TrimSpace(cursor))
	if err != nil {
		return model.RevisionPage{}, err
	}
	plan, found, err := reader.ReadByID(ctx, planID)
	if err != nil {
		return model.RevisionPage{}, err
	}
	if !found {
		return model.RevisionPage{}, model.ErrNotFound
	}
	items := make([]model.Revision, 0, limit)
	for _, revision := range plan.Revisions {
		if revision.RevisionNumber <= after {
			continue
		}
		items = append(items, revision)
		if len(items) == limit+1 {
			break
		}
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	page := model.RevisionPage{Items: items, HasMore: hasMore}
	if hasMore && len(items) > 0 {
		page.NextCursor = encodeRevisionCursor(planID, items[len(items)-1].RevisionNumber)
	}
	return page, nil
}

type revisionCursor struct {
	PlanID         string `json:"planId"`
	RevisionNumber int    `json:"revisionNumber"`
}

func encodeRevisionCursor(planID string, revisionNumber int) string {
	payload, _ := json.Marshal(revisionCursor{PlanID: planID, RevisionNumber: revisionNumber})
	return base64.RawURLEncoding.EncodeToString(payload)
}

func decodeRevisionCursor(planID, raw string) (int, error) {
	if raw == "" {
		return 0, nil
	}
	payload, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return 0, model.ErrCursorInvalid
	}
	var cursor revisionCursor
	decoderErr := json.Unmarshal(payload, &cursor)
	if decoderErr != nil || cursor.PlanID != planID || cursor.RevisionNumber <= 0 {
		return 0, model.ErrCursorInvalid
	}
	return cursor.RevisionNumber, nil
}

var _ ports.GatheringPlanReader = (*MongoGatheringPlanReader)(nil)
