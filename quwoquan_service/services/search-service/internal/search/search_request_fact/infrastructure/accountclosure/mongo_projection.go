package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	indexapplication "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
)

const (
	InboxCollection   = "search_user_account_closed_inbox"
	FailureCollection = "search_user_account_closed_failures"
)

const failureRetention = 7 * 24 * time.Hour

type inboxDocument struct {
	ID                      string    `bson:"_id"`
	EventDigest             string    `bson:"eventDigest"`
	DeletedRecentStates     int64     `bson:"deletedRecentStates"`
	DeletedRecentReceipts   int64     `bson:"deletedRecentReceipts"`
	DeletedQueries          int64     `bson:"deletedQueries"`
	DeletedFeedbackEvents   int64     `bson:"deletedFeedbackEvents"`
	DeletedFeedbackReceipts int64     `bson:"deletedFeedbackReceipts"`
	InvalidatedHeatTerms    int64     `bson:"invalidatedHeatTerms"`
	AppliedAt               time.Time `bson:"appliedAt"`
}

type failureDocument struct {
	Attempts       int64      `bson:"attempts"`
	DeadLetteredAt *time.Time `bson:"deadLetteredAt,omitempty"`
}

type cleanupResult struct {
	deletedRecentStates     int64
	deletedRecentReceipts   int64
	deletedQueries          int64
	deletedFeedbackEvents   int64
	deletedFeedbackReceipts int64
	invalidatedHeatTerms    int64
}

type MongoProjection struct {
	db               *mongo.Database
	recentStates     *mongo.Collection
	recentReceipts   *mongo.Collection
	queries          *mongo.Collection
	feedback         *mongo.Collection
	feedbackReceipts *mongo.Collection
	heat             *mongo.Collection
	inbox            *mongo.Collection
	failures         *mongo.Collection
	restrictions     indexapplication.SubjectClosureProjection
}

var _ application.UserAccountClosedProjection = (*MongoProjection)(nil)

func NewMongoProjection(
	db *mongo.Database,
	restrictions indexapplication.SubjectClosureProjection,
) (*MongoProjection, error) {
	if db == nil || restrictions == nil {
		return nil, errors.New(
			"search UserAccountClosed projection requires MongoDB and restriction closure projection",
		)
	}
	return &MongoProjection{
		db:               db,
		recentStates:     db.Collection("recent_search_states"),
		recentReceipts:   db.Collection("recent_search_receipts"),
		queries:          db.Collection("search_queries"),
		feedback:         db.Collection("search_feedback_events"),
		feedbackReceipts: db.Collection("search_feedback_command_receipts"),
		heat:             db.Collection("rm_search_term_heat"),
		inbox:            db.Collection(InboxCollection),
		failures:         db.Collection(FailureCollection),
		restrictions:     restrictions,
	}, nil
}

func (projection *MongoProjection) EnsureIndexes(ctx context.Context) error {
	if projection == nil || projection.db == nil {
		return errors.New("search UserAccountClosed projection is not configured")
	}
	if _, err := projection.inbox.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "appliedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_search_user_account_closed_applied"),
		},
	); err != nil {
		return fmt.Errorf("ensure search UserAccountClosed inbox index: %w", err)
	}
	if _, err := projection.failures.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{{Key: "eventDigest", Value: 1}},
				Options: options.Index().
					SetName("idx_search_user_account_closed_failure_event"),
			},
			{
				Keys: bson.D{{Key: "expireAt", Value: 1}},
				Options: options.Index().
					SetName("ttl_search_user_account_closed_failures").
					SetExpireAfterSeconds(0),
			},
		},
	); err != nil {
		return fmt.Errorf("ensure search UserAccountClosed failure indexes: %w", err)
	}
	if _, err := projection.queries.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{
				{Key: "viewerId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().
				SetName("idx_search_queries_viewer_created"),
		},
	); err != nil {
		return fmt.Errorf("ensure search query account cleanup index: %w", err)
	}
	if _, err := projection.feedback.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{
				{Key: "viewerId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().
				SetName("idx_search_feedback_viewer_created"),
		},
	); err != nil {
		return fmt.Errorf("ensure search feedback account cleanup index: %w", err)
	}
	if _, err := projection.feedbackReceipts.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: "viewerId", Value: 1},
					{Key: "createdAt", Value: -1},
				},
				Options: options.Index().
					SetName("idx_search_feedback_receipt_viewer_created"),
			},
			{
				Keys: bson.D{{Key: "searchRequestId", Value: 1}},
				Options: options.Index().
					SetName("idx_search_feedback_receipt_request"),
			},
		},
	); err != nil {
		return fmt.Errorf("ensure search feedback receipt cleanup indexes: %w", err)
	}
	if _, err := projection.recentReceipts.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "personaId", Value: 1}},
			Options: options.Index().
				SetName("idx_recent_search_receipts_persona"),
		},
	); err != nil {
		return fmt.Errorf("ensure recent search receipt cleanup index: %w", err)
	}
	return nil
}

func (projection *MongoProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if projection == nil || projection.db == nil {
		return application.UserAccountClosedProjectionResult{},
			errors.New("search UserAccountClosed projection is not configured")
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	if existing, found, err := projection.loadInbox(ctx, event.EventID); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	} else if found {
		return replayResult(existing, event)
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf("start search UserAccountClosed transaction: %w", err)
	}
	defer session.EndSession(ctx)

	result := application.UserAccountClosedProjectionResult{}
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			existing, found, loadErr := projection.loadInbox(
				txCtx,
				event.EventID,
			)
			if loadErr != nil {
				return nil, loadErr
			}
			if found {
				replayed, replayErr := replayResult(existing, event)
				result = replayed
				return nil, replayErr
			}
			cleanup, cleanupErr := projection.cleanupClosedSubjects(
				txCtx,
				event,
			)
			if cleanupErr != nil {
				return nil, cleanupErr
			}
			_, insertErr := projection.inbox.InsertOne(
				txCtx,
				inboxDocument{
					ID:                      event.EventID,
					EventDigest:             event.Digest(),
					DeletedRecentStates:     cleanup.deletedRecentStates,
					DeletedRecentReceipts:   cleanup.deletedRecentReceipts,
					DeletedQueries:          cleanup.deletedQueries,
					DeletedFeedbackEvents:   cleanup.deletedFeedbackEvents,
					DeletedFeedbackReceipts: cleanup.deletedFeedbackReceipts,
					InvalidatedHeatTerms:    cleanup.invalidatedHeatTerms,
					AppliedAt:               time.Now().UTC(),
				},
			)
			return nil, insertErr
		},
	)
	if err == nil {
		return result, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		existing, found, loadErr := projection.loadInbox(ctx, event.EventID)
		if loadErr != nil {
			return application.UserAccountClosedProjectionResult{}, loadErr
		}
		if found {
			return replayResult(existing, event)
		}
	}
	return application.UserAccountClosedProjectionResult{},
		fmt.Errorf("apply search UserAccountClosed cleanup: %w", err)
}

func (projection *MongoProjection) cleanupClosedSubjects(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (cleanupResult, error) {
	subjects := event.SubjectIDs()
	requestIDs, terms, err := projection.closedQueryInventory(ctx, subjects)
	if err != nil {
		return cleanupResult{}, err
	}
	if err := projection.restrictions.FinalizeClosure(
		ctx,
		indexapplication.SubjectClosure{
			EventDigest:    event.Digest(),
			AccountID:      event.UserID,
			AccountVersion: event.AccountVersion,
			ClosedAt:       event.UpdatedAt,
		},
	); err != nil {
		return cleanupResult{}, err
	}
	feedbackClauses := bson.A{
		bson.M{"viewerId": bson.M{"$in": subjects}},
	}
	if len(requestIDs) > 0 {
		feedbackClauses = append(
			feedbackClauses,
			bson.M{"searchRequestId": bson.M{"$in": requestIDs}},
		)
	}
	feedbackReceiptResult, err := projection.feedbackReceipts.DeleteMany(
		ctx,
		bson.M{"$or": feedbackClauses},
	)
	if err != nil {
		return cleanupResult{}, fmt.Errorf(
			"delete closed-account search feedback receipts: %w",
			err,
		)
	}
	feedbackResult, err := projection.feedback.DeleteMany(
		ctx,
		bson.M{"$or": feedbackClauses},
	)
	if err != nil {
		return cleanupResult{}, fmt.Errorf(
			"delete closed-account search feedback: %w",
			err,
		)
	}
	queryResult, err := projection.queries.DeleteMany(
		ctx,
		bson.M{"viewerId": bson.M{"$in": subjects}},
	)
	if err != nil {
		return cleanupResult{}, fmt.Errorf(
			"delete closed-account search queries: %w",
			err,
		)
	}
	stateResult, err := projection.recentStates.DeleteMany(
		ctx,
		bson.M{"personaId": bson.M{"$in": subjects}},
	)
	if err != nil {
		return cleanupResult{}, fmt.Errorf(
			"delete closed-account recent search states: %w",
			err,
		)
	}
	receiptResult, err := projection.recentReceipts.DeleteMany(
		ctx,
		bson.M{"personaId": bson.M{"$in": subjects}},
	)
	if err != nil {
		return cleanupResult{}, fmt.Errorf(
			"delete closed-account recent search receipts: %w",
			err,
		)
	}
	var heatDeleted int64
	if len(terms) > 0 {
		heatResult, deleteErr := projection.heat.DeleteMany(
			ctx,
			bson.M{"normalizedTerm": bson.M{"$in": terms}},
		)
		if deleteErr != nil {
			return cleanupResult{}, fmt.Errorf(
				"invalidate closed-account search heat: %w",
				deleteErr,
			)
		}
		heatDeleted = heatResult.DeletedCount
	}
	return cleanupResult{
		deletedRecentStates:     stateResult.DeletedCount,
		deletedRecentReceipts:   receiptResult.DeletedCount,
		deletedQueries:          queryResult.DeletedCount,
		deletedFeedbackEvents:   feedbackResult.DeletedCount,
		deletedFeedbackReceipts: feedbackReceiptResult.DeletedCount,
		invalidatedHeatTerms:    heatDeleted,
	}, nil
}

func (projection *MongoProjection) closedQueryInventory(
	ctx context.Context,
	subjects []string,
) ([]string, []string, error) {
	cursor, err := projection.queries.Find(
		ctx,
		bson.M{"viewerId": bson.M{"$in": subjects}},
		options.Find().SetProjection(bson.M{
			"searchRequestId": 1,
			"query":           1,
		}),
	)
	if err != nil {
		return nil, nil, fmt.Errorf(
			"scan closed-account search queries: %w",
			err,
		)
	}
	defer cursor.Close(ctx)
	var rows []struct {
		SearchRequestID string `bson:"searchRequestId"`
		Query           string `bson:"query"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, nil, fmt.Errorf(
			"decode closed-account search queries: %w",
			err,
		)
	}
	requestIDs := make([]string, 0, len(rows))
	terms := make([]string, 0, len(rows))
	requestSeen := make(map[string]struct{}, len(rows))
	termSeen := make(map[string]struct{}, len(rows))
	for _, row := range rows {
		if value := strings.TrimSpace(row.SearchRequestID); value != "" {
			if _, exists := requestSeen[value]; !exists {
				requestSeen[value] = struct{}{}
				requestIDs = append(requestIDs, value)
			}
		}
		if value := strings.TrimSpace(row.Query); value != "" {
			if _, exists := termSeen[value]; !exists {
				termSeen[value] = struct{}{}
				terms = append(terms, value)
			}
		}
	}
	return requestIDs, terms, nil
}

func (projection *MongoProjection) loadInbox(
	ctx context.Context,
	eventID string,
) (inboxDocument, bool, error) {
	var document inboxDocument
	err := projection.inbox.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(eventID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return inboxDocument{}, false, nil
	}
	if err != nil {
		return inboxDocument{}, false,
			fmt.Errorf("read search UserAccountClosed inbox: %w", err)
	}
	return document, true, nil
}

func replayResult(
	document inboxDocument,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if document.EventDigest != event.Digest() {
		return application.UserAccountClosedProjectionResult{},
			application.ErrUserAccountClosedEventIDConflict
	}
	return application.UserAccountClosedProjectionResult{Replayed: true}, nil
}
