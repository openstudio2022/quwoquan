package projection

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

var (
	ErrProjectionConflict = errors.New("assistant learning projection CAS conflict")
	ErrRebuildInProgress  = errors.New("assistant learning projection rebuild is in progress")
	ErrDefinitionMismatch = errors.New("assistant learning projection definition mismatch")
)

const (
	watermarkReady                     = "ready"
	watermarkRebuilding                = "rebuilding"
	activeDefinitionID                 = "active"
	projectionReceiptSequenceIndexName = "uq_assistant_learning_projection_receipt_sequence"
)

type activeDefinitionDocument struct {
	ID                string    `bson:"_id"`
	DefinitionVersion string    `bson:"definitionVersion"`
	GenerationID      string    `bson:"generationId"`
	UpdatedAt         time.Time `bson:"updatedAt"`
}

type watermarkDocument struct {
	ID                string    `bson:"_id"`
	DefinitionVersion string    `bson:"definitionVersion"`
	Sequence          int64     `bson:"sequence"`
	Status            string    `bson:"status"`
	UpdatedAt         time.Time `bson:"updatedAt"`
}

type receiptDocument struct {
	ID                 string    `bson:"_id"`
	EventID            string    `bson:"eventId"`
	EventVersion       int       `bson:"eventVersion"`
	AppendSequence     int64     `bson:"appendSequence"`
	DefinitionVersion  string    `bson:"definitionVersion"`
	GenerationID       string    `bson:"generationId"`
	ProjectionUserID   string    `bson:"projectionUserId"`
	ProjectionRevision int64     `bson:"projectionRevision"`
	ProjectedAt        time.Time `bson:"projectedAt"`
}

type MongoProjector struct {
	facts       *mongo.Collection
	projections *mongo.Collection
	receipts    *mongo.Collection
	watermarks  *mongo.Collection
}

func NewMongoProjector(database *mongo.Database) *MongoProjector {
	if database == nil {
		return &MongoProjector{}
	}
	return &MongoProjector{
		facts:       database.Collection("assistant_learning_facts"),
		projections: database.Collection("rm_assistant_learning_projection"),
		receipts:    database.Collection("assistant_learning_projection_receipts"),
		watermarks:  database.Collection("assistant_learning_projection_watermarks"),
	}
}

func (projector *MongoProjector) EnsureIndexes(ctx context.Context) error {
	if !projector.ready() {
		return learningapplication.ErrStoreUnavailable
	}
	if _, err := projector.projections.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: "userId", Value: 1},
					{Key: "personaId", Value: 1},
					{Key: "updatedAt", Value: -1},
				},
				Options: options.Index().
					SetName("idx_assistant_learning_projection_owner_updated"),
			},
			{
				Keys: bson.D{{Key: "watermarkSequence", Value: 1}},
				Options: options.Index().
					SetName("idx_assistant_learning_projection_watermark"),
			},
		},
	); err != nil {
		return fmt.Errorf("ensure learning projection indexes: %w", err)
	}
	if err := projector.ensureProjectionReceiptSequenceIndex(ctx); err != nil {
		return fmt.Errorf("ensure learning projection receipt indexes: %w", err)
	}
	if _, err := projector.watermarks.UpdateOne(
		ctx,
		bson.M{"_id": activeDefinitionID},
		bson.M{"$setOnInsert": bson.M{
			"definitionVersion": model.LearningProjectionDefinitionVersion,
			"generationId":      model.LearningProjectionDefinitionVersion,
			"updatedAt":         time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	); err != nil {
		return fmt.Errorf("ensure active learning projection definition: %w", err)
	}
	return nil
}

func (projector *MongoProjector) ensureProjectionReceiptSequenceIndex(
	ctx context.Context,
) error {
	indexes := projector.receipts.Indexes()
	specifications, err := indexes.ListSpecifications(ctx)
	if err != nil {
		return err
	}
	for _, specification := range specifications {
		if specification.Name != projectionReceiptSequenceIndexName {
			continue
		}
		if isProjectionReceiptSequenceIndex(specification) {
			return nil
		}
		if err := indexes.DropOne(ctx, projectionReceiptSequenceIndexName); err != nil {
			return fmt.Errorf(
				"replace obsolete projection receipt index %s: %w",
				projectionReceiptSequenceIndexName,
				err,
			)
		}
		break
	}
	_, err = indexes.CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{
				{Key: "generationId", Value: 1},
				{Key: "appendSequence", Value: 1},
			},
			Options: options.Index().
				SetName(projectionReceiptSequenceIndexName).
				SetUnique(true),
		},
	)
	return err
}

func isProjectionReceiptSequenceIndex(specification mongo.IndexSpecification) bool {
	if specification.Name != projectionReceiptSequenceIndexName ||
		specification.Unique == nil ||
		!*specification.Unique {
		return false
	}
	var keys bson.D
	if err := bson.Unmarshal(specification.KeysDocument, &keys); err != nil {
		return false
	}
	return len(keys) == 2 &&
		keys[0].Key == "generationId" && keys[0].Value == int32(1) &&
		keys[1].Key == "appendSequence" && keys[1].Value == int32(1)
}

// ProjectAvailable applies at most limit facts in global append order.
// Every fact receipt, owner projection and global watermark are committed by
// one Mongo transaction; a failed callback cannot advance the checkpoint.
func (projector *MongoProjector) ProjectAvailable(
	ctx context.Context,
	limit int,
) (int, error) {
	if limit <= 0 {
		limit = 256
	}
	active, err := projector.loadActiveDefinition(ctx)
	if err != nil {
		return 0, err
	}
	if active.DefinitionVersion != model.LearningProjectionDefinitionVersion {
		return 0, ErrDefinitionMismatch
	}
	projected := 0
	for projected < limit {
		applied, err := projector.projectNext(ctx, false, active.GenerationID)
		if errors.Is(err, ErrProjectionConflict) {
			continue
		}
		if err != nil {
			return projected, err
		}
		if !applied {
			return projected, nil
		}
		projected++
	}
	return projected, nil
}

func (projector *MongoProjector) GetLearningProjection(
	ctx context.Context,
	userID string,
) (*model.LearningProjection, error) {
	if !projector.ready() {
		return nil, learningapplication.ErrStoreUnavailable
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil, nil
	}
	active, err := projector.loadActiveDefinition(ctx)
	if err != nil {
		return nil, fmt.Errorf("read active learning projection definition: %w", err)
	}
	if active.DefinitionVersion != model.LearningProjectionDefinitionVersion {
		return nil, ErrDefinitionMismatch
	}
	cursor, err := projector.projections.Find(
		ctx,
		bson.M{
			"userId":       userID,
			"generationId": active.GenerationID,
		},
		options.Find().SetSort(
			bson.D{
				{Key: "updatedAt", Value: -1},
				{Key: "personaId", Value: 1},
			},
		),
	)
	if err != nil {
		return nil, fmt.Errorf("read assistant learning projection: %w", err)
	}
	defer cursor.Close(ctx)
	var aggregate *model.LearningProjection
	for cursor.Next(ctx) {
		var projection model.LearningProjection
		if err := cursor.Decode(&projection); err != nil {
			return nil, fmt.Errorf("decode assistant learning projection: %w", err)
		}
		if projection.DefinitionVersion !=
			model.LearningProjectionDefinitionVersion {
			return nil, ErrDefinitionMismatch
		}
		if aggregate == nil {
			initial := model.NewLearningProjectionAggregate(
				active.GenerationID,
				userID,
			)
			aggregate = &initial
		}
		model.MergeLearningProjection(aggregate, projection)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate assistant learning projection: %w", err)
	}
	return aggregate, nil
}

// GetLearningProjectionForPersona reads only the projection bound to the
// authenticated account/persona pair. It is the only reader permitted for
// model feedback-context injection.
func (projector *MongoProjector) GetLearningProjectionForPersona(
	ctx context.Context,
	userID string,
	personaID string,
) (*model.LearningProjection, error) {
	if !projector.ready() {
		return nil, learningapplication.ErrStoreUnavailable
	}
	userID = strings.TrimSpace(userID)
	personaID = strings.TrimSpace(personaID)
	if userID == "" || personaID == "" {
		return nil, nil
	}
	active, err := projector.loadActiveDefinition(ctx)
	if err != nil {
		return nil, fmt.Errorf("read active learning projection definition: %w", err)
	}
	if active.DefinitionVersion != model.LearningProjectionDefinitionVersion {
		return nil, ErrDefinitionMismatch
	}
	var projection model.LearningProjection
	err = projector.projections.FindOne(
		ctx,
		bson.M{
			"_id": model.ProjectionStorageID(
				active.GenerationID,
				userID,
				personaID,
			),
		},
	).Decode(&projection)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read assistant persona learning projection: %w", err)
	}
	if projection.DefinitionVersion != model.LearningProjectionDefinitionVersion ||
		projection.UserID != userID ||
		projection.PersonaID != personaID {
		return nil, ErrDefinitionMismatch
	}
	return &projection, nil
}

// Rebuild replaces all projection state from the sole canonical fact stream.
// The durable rebuilding watermark blocks normal projectors until catch-up
// and the final ready transition both succeed.
func (projector *MongoProjector) Rebuild(ctx context.Context) (int, error) {
	if !projector.ready() {
		return 0, learningapplication.ErrStoreUnavailable
	}
	generationID := fmt.Sprintf(
		"%s:rebuild:%d",
		model.LearningProjectionDefinitionVersion,
		time.Now().UTC().UnixNano(),
	)
	if err := projector.beginRebuild(ctx, generationID); err != nil {
		return 0, err
	}
	projected := 0
	for {
		applied, err := projector.projectNext(ctx, true, generationID)
		if errors.Is(err, ErrProjectionConflict) {
			continue
		}
		if err != nil {
			return projected, err
		}
		if !applied {
			break
		}
		projected++
	}
	if err := projector.finishRebuild(ctx, generationID); err != nil {
		return projected, err
	}
	return projected, nil
}

func (projector *MongoProjector) projectNext(
	ctx context.Context,
	duringRebuild bool,
	generationID string,
) (bool, error) {
	if !projector.ready() {
		return false, learningapplication.ErrStoreUnavailable
	}
	session, err := projector.facts.Database().Client().StartSession()
	if err != nil {
		return false, fmt.Errorf("start learning projection transaction: %w", err)
	}
	defer session.EndSession(ctx)

	applied := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		watermark, loadErr := projector.loadWatermark(txCtx, generationID)
		if loadErr != nil {
			return nil, loadErr
		}
		if watermark.Status == watermarkRebuilding && !duringRebuild {
			return nil, ErrRebuildInProgress
		}
		if watermark.Status != watermarkRebuilding && duringRebuild {
			return nil, ErrProjectionConflict
		}
		var fact model.Fact
		factErr := projector.facts.FindOne(
			txCtx,
			bson.M{"appendSequence": watermark.Sequence + 1},
		).Decode(&fact)
		if errors.Is(factErr, mongo.ErrNoDocuments) {
			return nil, nil
		}
		if factErr != nil {
			return nil, factErr
		}

		current, found, projectionErr := projector.loadProjection(
			txCtx,
			fact.UserID,
			fact.PersonaID,
			generationID,
		)
		if projectionErr != nil {
			return nil, projectionErr
		}
		if found &&
			current.DefinitionVersion != model.LearningProjectionDefinitionVersion {
			return nil, ErrDefinitionMismatch
		}
		next := model.ApplyLearningFact(current, fact)
		next.StorageID = model.ProjectionStorageID(
			generationID,
			next.UserID,
			next.PersonaID,
		)
		next.GenerationID = generationID
		if err := projector.replaceProjection(txCtx, current, next, found); err != nil {
			return nil, err
		}
		now := time.Now().UTC()
		if _, receiptErr := projector.receipts.InsertOne(
			txCtx,
			receiptDocument{
				ID: generationID + ":" +
					fact.StorageID,
				EventID:            fact.EventID,
				EventVersion:       fact.EventVersion,
				AppendSequence:     fact.AppendSequence,
				DefinitionVersion:  model.LearningProjectionDefinitionVersion,
				GenerationID:       generationID,
				ProjectionUserID:   next.UserID,
				ProjectionRevision: next.Revision,
				ProjectedAt:        now,
			},
		); receiptErr != nil {
			return nil, receiptErr
		}
		nextWatermark := watermark
		nextWatermark.Sequence = fact.AppendSequence
		nextWatermark.UpdatedAt = now
		if err := projector.replaceWatermark(
			txCtx,
			watermark,
			nextWatermark,
		); err != nil {
			return nil, err
		}
		applied = true
		return nil, nil
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return false, ErrProjectionConflict
		}
		return false, err
	}
	return applied, nil
}

func (projector *MongoProjector) beginRebuild(
	ctx context.Context,
	generationID string,
) error {
	_, err := projector.watermarks.InsertOne(ctx, watermarkDocument{
		ID:                generationID,
		DefinitionVersion: model.LearningProjectionDefinitionVersion,
		Status:            watermarkRebuilding,
		UpdatedAt:         time.Now().UTC(),
	})
	if mongo.IsDuplicateKeyError(err) {
		return ErrRebuildInProgress
	}
	return err
}

func (projector *MongoProjector) finishRebuild(
	ctx context.Context,
	generationID string,
) error {
	session, err := projector.facts.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		now := time.Now().UTC()
		result, updateErr := projector.watermarks.UpdateOne(
			txCtx,
			bson.M{
				"_id":    generationID,
				"status": watermarkRebuilding,
			},
			bson.M{
				"$set": bson.M{
					"status":    watermarkReady,
					"updatedAt": now,
				},
			},
		)
		if updateErr != nil {
			return nil, updateErr
		}
		if result.MatchedCount != 1 {
			return nil, ErrProjectionConflict
		}
		_, updateErr = projector.watermarks.UpdateOne(
			txCtx,
			bson.M{"_id": activeDefinitionID},
			bson.M{"$set": bson.M{
				"definitionVersion": model.LearningProjectionDefinitionVersion,
				"generationId":      generationID,
				"updatedAt":         now,
			}},
			options.UpdateOne().SetUpsert(true),
		)
		return nil, updateErr
	})
	return err
}

func (projector *MongoProjector) loadWatermark(
	ctx context.Context,
	generationID string,
) (watermarkDocument, error) {
	var document watermarkDocument
	err := projector.watermarks.FindOne(
		ctx,
		bson.M{"_id": generationID},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return watermarkDocument{
			ID:                generationID,
			DefinitionVersion: model.LearningProjectionDefinitionVersion,
			Status:            watermarkReady,
		}, nil
	}
	if err != nil {
		return watermarkDocument{}, err
	}
	return document, nil
}

func (projector *MongoProjector) loadActiveDefinition(
	ctx context.Context,
) (activeDefinitionDocument, error) {
	var active activeDefinitionDocument
	err := projector.watermarks.FindOne(
		ctx,
		bson.M{"_id": activeDefinitionID},
	).Decode(&active)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return activeDefinitionDocument{
			ID:                activeDefinitionID,
			DefinitionVersion: model.LearningProjectionDefinitionVersion,
			GenerationID:      model.LearningProjectionDefinitionVersion,
		}, nil
	}
	if err != nil {
		return activeDefinitionDocument{}, err
	}
	active.DefinitionVersion = strings.TrimSpace(active.DefinitionVersion)
	active.GenerationID = strings.TrimSpace(active.GenerationID)
	if active.DefinitionVersion == "" || active.GenerationID == "" {
		return activeDefinitionDocument{}, ErrDefinitionMismatch
	}
	return active, nil
}

func (projector *MongoProjector) replaceWatermark(
	ctx context.Context,
	current watermarkDocument,
	next watermarkDocument,
) error {
	filter := bson.M{
		"_id":      current.ID,
		"sequence": current.Sequence,
		"status":   current.Status,
	}
	result, err := projector.watermarks.ReplaceOne(
		ctx,
		filter,
		next,
		options.Replace().SetUpsert(current.UpdatedAt.IsZero()),
	)
	if err != nil {
		return err
	}
	if result.MatchedCount == 0 && result.UpsertedCount == 0 {
		return ErrProjectionConflict
	}
	return nil
}

func (projector *MongoProjector) loadProjection(
	ctx context.Context,
	userID string,
	personaID string,
	generationID string,
) (model.LearningProjection, bool, error) {
	var projection model.LearningProjection
	err := projector.projections.FindOne(
		ctx,
		bson.M{
			"_id": model.ProjectionStorageID(generationID, userID, personaID),
		},
	).Decode(&projection)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.LearningProjection{}, false, nil
	}
	if err != nil {
		return model.LearningProjection{}, false, err
	}
	return projection, true, nil
}

func (projector *MongoProjector) replaceProjection(
	ctx context.Context,
	current model.LearningProjection,
	next model.LearningProjection,
	found bool,
) error {
	if !found {
		_, err := projector.projections.InsertOne(ctx, next)
		return err
	}
	result, err := projector.projections.ReplaceOne(
		ctx,
		bson.M{
			"_id":               current.StorageID,
			"revision":          current.Revision,
			"definitionVersion": current.DefinitionVersion,
		},
		next,
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return ErrProjectionConflict
	}
	return nil
}

func (projector *MongoProjector) ready() bool {
	return projector != nil &&
		projector.facts != nil &&
		projector.projections != nil &&
		projector.receipts != nil &&
		projector.watermarks != nil
}
