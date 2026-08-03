// Package queryheatstore is the MongoDB persistence for the derived search-term
// heat read model (rm_search_term_heat). It mines SearchRequestFact locally and
// consumes SearchFeedbackFact through its typed reader; sibling collections are
// never opened here. The pure queryheat algorithm remains storage agnostic.
//
// Single source: the heat read model is REBUILDABLE from the logs; it is never
// a source of truth. TTL (storage.yaml collections.rm_search_term_heat)
// recycles stale aggregates so the served heat always reflects a recent window.
package queryheatstore

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
)

const (
	queriesCollection = "search_queries"
	heatCollection    = "rm_search_term_heat"

	// HeatTTLSeconds — single source: storage.yaml collections
	// .rm_search_term_heat.ttl.seconds (24h). Exported + pinned by a contract test.
	HeatTTLSeconds = 86400

	// miningWindow bounds how far back the builder scans the logs so a rebuild
	// is O(recent traffic), and maxScan caps memory for a single rebuild.
	miningWindow = 30 * 24 * time.Hour
	maxScan      = 50000
	// servedTopK caps how many heat rows the provider loads per request before
	// the pure RelatedTerms filter narrows them to the query.
	servedTopK = 200
)

// Store builds + serves the rm_search_term_heat read model.
type Store struct {
	queries  *mongo.Collection
	heat     *mongo.Collection
	feedback feedbackapplication.HeatReader
	cfg      queryheat.Config
	logger   *slog.Logger
}

// NewStore wires the collections and ensures the read-model indexes + TTL.
func NewStore(
	db *mongo.Database,
	feedback feedbackapplication.HeatReader,
	cfg queryheat.Config,
	logger *slog.Logger,
) *Store {
	if db == nil || feedback == nil {
		panic("SearchTermHeatView requires MongoDB and SearchFeedbackFact reader")
	}
	if logger == nil {
		logger = slog.Default()
	}
	s := &Store{
		queries:  db.Collection(queriesCollection),
		heat:     db.Collection(heatCollection),
		feedback: feedback,
		cfg:      cfg,
		logger:   logger,
	}
	s.ensureIndexes()
	return s
}

func (s *Store) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "normalizedTerm", Value: 1}},
			Options: options.Index().SetUnique(true).SetName("idx_search_term_heat_term"),
		},
		{
			Keys:    bson.D{{Key: "relevance", Value: -1}},
			Options: options.Index().SetName("idx_search_term_heat_relevance"),
		},
		{
			Keys:    bson.D{{Key: "updatedAt", Value: 1}},
			Options: options.Index().SetName("idx_search_term_heat_ttl").SetExpireAfterSeconds(int32(HeatTTLSeconds)),
		},
	}
	for _, idx := range indexes {
		if _, err := s.heat.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("queryheatstore: index creation failed", slog.String("error", err.Error()))
		}
	}
}

type queryRow struct {
	SearchRequestID string    `bson:"searchRequestId"`
	Query           string    `bson:"query"`
	CreatedAt       time.Time `bson:"createdAt"`
	ResultCount     int       `bson:"resultCount"`
}

type heatRow struct {
	queryheat.TermHeat `bson:",inline"`
	UpdatedAt          time.Time `bson:"updatedAt"`
}

// Rebuild mines the recent logs into the heat read model and upserts every term
// row. It returns the number of terms written. Callers run it on a schedule; it
// is idempotent and safe to run concurrently with reads (per-term upserts).
func (s *Store) Rebuild(ctx context.Context) (int, error) {
	since := time.Now().UTC().Add(-miningWindow)

	queries, termByRequest, err := s.loadQueries(ctx, since)
	if err != nil {
		return 0, err
	}
	feedback, err := s.loadFeedback(ctx, since, termByRequest)
	if err != nil {
		return 0, err
	}

	heats := queryheat.Compute(queries, feedback, s.cfg)
	now := time.Now().UTC()
	written := 0
	for _, h := range heats {
		row := heatRow{TermHeat: h, UpdatedAt: now}
		if _, err := s.heat.ReplaceOne(ctx,
			bson.M{"normalizedTerm": h.NormalizedTerm}, row,
			options.Replace().SetUpsert(true),
		); err != nil {
			s.logger.Warn("queryheatstore: heat upsert failed",
				slog.String("term", h.NormalizedTerm), slog.String("error", err.Error()))
			continue
		}
		written++
	}
	return written, nil
}

func (s *Store) loadQueries(ctx context.Context, since time.Time) ([]queryheat.QueryRecord, map[string]string, error) {
	cursor, err := s.queries.Find(ctx,
		bson.M{"createdAt": bson.M{"$gte": since}},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(maxScan),
	)
	if err != nil {
		return nil, nil, err
	}
	defer cursor.Close(ctx)

	records := make([]queryheat.QueryRecord, 0, 256)
	termByRequest := make(map[string]string, 256)
	for cursor.Next(ctx) {
		var row queryRow
		if err := cursor.Decode(&row); err != nil {
			s.logger.Warn("queryheatstore: decode query row failed", slog.String("error", err.Error()))
			continue
		}
		records = append(records, queryheat.QueryRecord{
			NormalizedTerm: row.Query,
			CreatedAt:      row.CreatedAt,
			ResultCount:    row.ResultCount,
		})
		if row.SearchRequestID != "" {
			termByRequest[row.SearchRequestID] = row.Query
		}
	}
	return records, termByRequest, cursor.Err()
}

func (s *Store) loadFeedback(ctx context.Context, since time.Time, termByRequest map[string]string) ([]queryheat.FeedbackRecord, error) {
	rows, err := s.feedback.ListHeatFeedback(ctx, since, maxScan)
	if err != nil {
		return nil, err
	}
	records := make([]queryheat.FeedbackRecord, 0, 256)
	for _, row := range rows {
		term, ok := termByRequest[row.SearchRequestID]
		if !ok || term == "" {
			// The originating query is outside the window or unlogged; skip
			// rather than attributing the interaction to an unknown term.
			continue
		}
		records = append(records, queryheat.FeedbackRecord{
			NormalizedTerm: term,
			EventType:      row.EventType,
			ObjectID:       row.ObjectID,
			CreatedAt:      row.CreatedAt,
		})
	}
	return records, nil
}

// RelatedTerms loads the hottest heat rows and narrows them to normalizedQuery
// with the pure RelatedTerms selector (single-sourced matching). It implements
// application.TermHeatProvider.
func (s *Store) RelatedTerms(ctx context.Context, normalizedQuery string, limit int) ([]queryheat.TermHeat, error) {
	cursor, err := s.heat.Find(ctx, bson.M{},
		options.Find().SetSort(bson.D{{Key: "relevance", Value: -1}}).SetLimit(servedTopK),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	heats := make([]queryheat.TermHeat, 0, servedTopK)
	for cursor.Next(ctx) {
		var row heatRow
		if err := cursor.Decode(&row); err != nil {
			s.logger.Warn("queryheatstore: decode heat row failed", slog.String("error", err.Error()))
			continue
		}
		heats = append(heats, row.TermHeat)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return queryheat.RelatedTerms(normalizedQuery, heats, limit), nil
}
