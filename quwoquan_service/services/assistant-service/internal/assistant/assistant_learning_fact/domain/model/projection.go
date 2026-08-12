package model

import (
	"crypto/rand"
	"encoding/hex"
	"sort"
	"strings"
	"time"
)

// LearningProjectionDefinitionDigest is the SHA-256 identity of the sole
// canonical learning projection contract. A stored mismatch is never read as
// compatible state; the projector must rebuild from canonical facts.
const LearningProjectionDefinitionDigest = "a445f797a6cf5ba088b127ae3208564a58b35c7bff870786c7e60819174fee10"

const learningProjectionGenerationPrefix = "rebuild:"

// NewLearningProjectionGenerationID returns an opaque identity for exactly one
// rebuild execution. It does not encode a model or contract definition.
func NewLearningProjectionGenerationID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	return learningProjectionGenerationPrefix + hex.EncodeToString(random), nil
}

func IsLearningProjectionGenerationID(value string) bool {
	value = strings.TrimSpace(value)
	if !strings.HasPrefix(value, learningProjectionGenerationPrefix) {
		return false
	}
	encoded := strings.TrimPrefix(value, learningProjectionGenerationPrefix)
	decoded, err := hex.DecodeString(encoded)
	return err == nil && len(decoded) == 16 && encoded == strings.ToLower(encoded)
}

// AssistantLearningOpsSummaryView is the object-owned operator projection
// returned by GetLearningOpsSummary. It intentionally exposes only redacted
// aggregate counters and scores; raw feedback/query/answer text never crosses
// the operations boundary.
type AssistantLearningOpsSummaryView struct {
	UserID                string             `json:"userId"`
	TotalFeedbackCount    int64              `json:"totalFeedbackCount"`
	PositiveFeedbackCount int64              `json:"positiveFeedbackCount"`
	NegativeFeedbackCount int64              `json:"negativeFeedbackCount"`
	TextFeedbackCount     int64              `json:"textFeedbackCount"`
	HighPriorityCount     int64              `json:"highPriorityCount"`
	MediumPriorityCount   int64              `json:"mediumPriorityCount"`
	LastFeedbackType      string             `json:"lastFeedbackType,omitempty"`
	LastFeedbackScore     float64            `json:"lastFeedbackScore,omitempty"`
	LastFeedbackAt        string             `json:"lastFeedbackAt,omitempty"`
	LastMetricID          string             `json:"lastMetricId,omitempty"`
	LastMetricScore       float64            `json:"lastMetricScore,omitempty"`
	TopReasonCodes        []string           `json:"topReasonCodes,omitempty"`
	MetricAverages        map[string]float64 `json:"metricAverages,omitempty"`
	LatestMetricScores    map[string]float64 `json:"latestMetricScores,omitempty"`
	UpdatedAt             string             `json:"updatedAt,omitempty"`
}

type LearningProjectionBucket struct {
	FeedbackCount         int64              `bson:"feedbackCount" json:"feedbackCount"`
	PositiveFeedbackCount int64              `bson:"positiveFeedbackCount" json:"positiveFeedbackCount"`
	NegativeFeedbackCount int64              `bson:"negativeFeedbackCount" json:"negativeFeedbackCount"`
	TextFeedbackCount     int64              `bson:"textFeedbackCount" json:"textFeedbackCount"`
	MetricSampleCounts    map[string]int64   `bson:"metricSampleCounts" json:"metricSampleCounts"`
	MetricScoreSums       map[string]float64 `bson:"metricScoreSums" json:"metricScoreSums"`
	LatestMetricScores    map[string]float64 `bson:"latestMetricScores" json:"latestMetricScores"`
	ReasonCodeCounts      map[string]int64   `bson:"reasonCodeCounts" json:"reasonCodeCounts"`
}

// LearningProjection is a rebuildable, redacted owner-scoped read model.
// Raw query, answer, feedback and correction text never enter this document.
type LearningProjection struct {
	StorageID             string                              `bson:"_id" json:"-"`
	UserID                string                              `bson:"userId" json:"userId"`
	PersonaID             string                              `bson:"personaId" json:"personaId"`
	DefinitionDigest      string                              `bson:"definitionDigest" json:"definitionDigest"`
	GenerationID          string                              `bson:"generationId" json:"generationId"`
	Revision              int64                               `bson:"revision" json:"revision"`
	WatermarkSequence     int64                               `bson:"watermarkSequence" json:"watermarkSequence"`
	LastAssistantTurnID   string                              `bson:"lastAssistantTurnId,omitempty" json:"lastAssistantTurnId,omitempty"`
	LastEventID           string                              `bson:"lastEventId,omitempty" json:"lastEventId,omitempty"`
	LastFeedbackType      string                              `bson:"lastFeedbackType,omitempty" json:"lastFeedbackType,omitempty"`
	LastFeedbackScore     float64                             `bson:"lastFeedbackScore,omitempty" json:"lastFeedbackScore,omitempty"`
	LastFeedbackAt        time.Time                           `bson:"lastFeedbackAt,omitempty" json:"lastFeedbackAt,omitempty"`
	LastMetricID          string                              `bson:"lastMetricId,omitempty" json:"lastMetricId,omitempty"`
	LastMetricScore       float64                             `bson:"lastMetricScore,omitempty" json:"lastMetricScore,omitempty"`
	TotalFeedbackCount    int64                               `bson:"totalFeedbackCount" json:"totalFeedbackCount"`
	PositiveFeedbackCount int64                               `bson:"positiveFeedbackCount" json:"positiveFeedbackCount"`
	NegativeFeedbackCount int64                               `bson:"negativeFeedbackCount" json:"negativeFeedbackCount"`
	TextFeedbackCount     int64                               `bson:"textFeedbackCount" json:"textFeedbackCount"`
	HighPriorityCount     int64                               `bson:"highPriorityCount" json:"highPriorityCount"`
	MediumPriorityCount   int64                               `bson:"mediumPriorityCount" json:"mediumPriorityCount"`
	MetricSampleCounts    map[string]int64                    `bson:"metricSampleCounts" json:"metricSampleCounts"`
	MetricScoreSums       map[string]float64                  `bson:"metricScoreSums" json:"metricScoreSums"`
	LatestMetricScores    map[string]float64                  `bson:"latestMetricScores" json:"latestMetricScores"`
	ReasonCodeCounts      map[string]int64                    `bson:"reasonCodeCounts" json:"reasonCodeCounts"`
	DailyBuckets          map[string]LearningProjectionBucket `bson:"dailyBuckets" json:"dailyBuckets"`
	UpdatedAt             time.Time                           `bson:"updatedAt" json:"updatedAt"`
}

func NewLearningProjection(
	generationID string,
	fact Fact,
) LearningProjection {
	generationID = strings.TrimSpace(generationID)
	return LearningProjection{
		StorageID:          ProjectionStorageID(generationID, fact.UserID, fact.PersonaID),
		UserID:             fact.UserID,
		PersonaID:          fact.PersonaID,
		DefinitionDigest:   LearningProjectionDefinitionDigest,
		GenerationID:       generationID,
		MetricSampleCounts: map[string]int64{},
		MetricScoreSums:    map[string]float64{},
		LatestMetricScores: map[string]float64{},
		ReasonCodeCounts:   map[string]int64{},
		DailyBuckets:       map[string]LearningProjectionBucket{},
	}
}

// ProjectionStorageID binds each projection generation to the complete actor
// owner. A user can switch personas; facts from one persona must never become
// feedback context for another persona.
func ProjectionStorageID(
	generationID string,
	userID string,
	personaID string,
) string {
	return strings.TrimSpace(generationID) + ":" +
		strings.TrimSpace(userID) + ":" +
		strings.TrimSpace(personaID)
}

func NewLearningProjectionAggregate(
	generationID string,
	userID string,
) LearningProjection {
	generationID = strings.TrimSpace(generationID)
	userID = strings.TrimSpace(userID)
	return LearningProjection{
		StorageID:          generationID + ":" + userID + ":account_aggregate",
		UserID:             userID,
		DefinitionDigest:   LearningProjectionDefinitionDigest,
		GenerationID:       generationID,
		MetricSampleCounts: map[string]int64{},
		MetricScoreSums:    map[string]float64{},
		LatestMetricScores: map[string]float64{},
		ReasonCodeCounts:   map[string]int64{},
		DailyBuckets:       map[string]LearningProjectionBucket{},
	}
}

func MergeLearningProjection(
	aggregate *LearningProjection,
	source LearningProjection,
) {
	if aggregate == nil {
		return
	}
	aggregate.Revision += source.Revision
	if source.WatermarkSequence > aggregate.WatermarkSequence {
		aggregate.WatermarkSequence = source.WatermarkSequence
	}
	aggregate.TotalFeedbackCount += source.TotalFeedbackCount
	aggregate.PositiveFeedbackCount += source.PositiveFeedbackCount
	aggregate.NegativeFeedbackCount += source.NegativeFeedbackCount
	aggregate.TextFeedbackCount += source.TextFeedbackCount
	aggregate.HighPriorityCount += source.HighPriorityCount
	aggregate.MediumPriorityCount += source.MediumPriorityCount
	mergeInt64Map(aggregate.MetricSampleCounts, source.MetricSampleCounts)
	mergeFloat64Map(aggregate.MetricScoreSums, source.MetricScoreSums)
	mergeInt64Map(aggregate.ReasonCodeCounts, source.ReasonCodeCounts)
	for metricID, score := range source.LatestMetricScores {
		if _, exists := aggregate.LatestMetricScores[metricID]; !exists {
			aggregate.LatestMetricScores[metricID] = score
		}
	}
	for day, sourceBucket := range source.DailyBuckets {
		bucket := aggregate.DailyBuckets[day]
		ensureBucketMaps(&bucket)
		bucket.FeedbackCount += sourceBucket.FeedbackCount
		bucket.PositiveFeedbackCount += sourceBucket.PositiveFeedbackCount
		bucket.NegativeFeedbackCount += sourceBucket.NegativeFeedbackCount
		bucket.TextFeedbackCount += sourceBucket.TextFeedbackCount
		mergeInt64Map(bucket.MetricSampleCounts, sourceBucket.MetricSampleCounts)
		mergeFloat64Map(bucket.MetricScoreSums, sourceBucket.MetricScoreSums)
		mergeInt64Map(bucket.ReasonCodeCounts, sourceBucket.ReasonCodeCounts)
		for metricID, score := range sourceBucket.LatestMetricScores {
			if _, exists := bucket.LatestMetricScores[metricID]; !exists {
				bucket.LatestMetricScores[metricID] = score
			}
		}
		aggregate.DailyBuckets[day] = bucket
	}
	if aggregate.UpdatedAt.IsZero() || source.UpdatedAt.After(aggregate.UpdatedAt) {
		aggregate.LastAssistantTurnID = source.LastAssistantTurnID
		aggregate.LastEventID = source.LastEventID
		aggregate.LastFeedbackType = source.LastFeedbackType
		aggregate.LastFeedbackScore = source.LastFeedbackScore
		aggregate.LastFeedbackAt = source.LastFeedbackAt
		aggregate.LastMetricID = source.LastMetricID
		aggregate.LastMetricScore = source.LastMetricScore
		aggregate.UpdatedAt = source.UpdatedAt
	}
}

func mergeInt64Map(target map[string]int64, source map[string]int64) {
	for key, value := range source {
		target[key] += value
	}
}

func mergeFloat64Map(target map[string]float64, source map[string]float64) {
	for key, value := range source {
		target[key] += value
	}
}

// ApplyLearningFact is deterministic and order-sensitive only through the
// server append sequence. Replaying the same ordered fact stream yields the
// same projection bytes apart from Mongo's internal encoding.
func ApplyLearningFact(
	projection LearningProjection,
	fact Fact,
	generationID string,
) LearningProjection {
	if projection.UserID == "" {
		projection = NewLearningProjection(generationID, fact)
	}
	ensureProjectionMaps(&projection)
	projection.DefinitionDigest = LearningProjectionDefinitionDigest
	projection.GenerationID = strings.TrimSpace(generationID)
	projection.PersonaID = fact.PersonaID
	projection.Revision++
	projection.WatermarkSequence = fact.AppendSequence
	projection.LastAssistantTurnID = fact.AssistantTurnID
	projection.LastEventID = fact.EventID
	projection.UpdatedAt = fact.RecordedAt

	priority := learningFactPriority(fact)
	switch priority {
	case "high":
		projection.HighPriorityCount++
	case "medium":
		projection.MediumPriorityCount++
	}

	switch fact.FactType {
	case FactTypeUserFeedback:
		projection.TotalFeedbackCount++
		projection.LastFeedbackType = fact.FeedbackType
		projection.LastFeedbackScore = fact.FeedbackScore
		projection.LastFeedbackAt = fact.OccurredAt
		switch strings.TrimSpace(fact.FeedbackType) {
		case "thumbs_up", "useful":
			projection.PositiveFeedbackCount++
		case "thumbs_down", "irrelevant", "too_frequent":
			projection.NegativeFeedbackCount++
		case "text":
			projection.TextFeedbackCount++
		}
		for _, reason := range fact.ReasonCodes {
			projection.ReasonCodeCounts[reason]++
		}
	case FactTypeServiceScorecard:
		projection.LastMetricID = fact.MetricID
		projection.LastMetricScore = fact.MetricValue
		projection.MetricSampleCounts[fact.MetricID]++
		projection.MetricScoreSums[fact.MetricID] += fact.MetricValue
		projection.LatestMetricScores[fact.MetricID] = fact.MetricValue
	}
	applyDailyBucket(&projection, fact)
	return projection
}

func applyDailyBucket(projection *LearningProjection, fact Fact) {
	occurredAt := fact.OccurredAt.UTC()
	if occurredAt.IsZero() {
		occurredAt = fact.RecordedAt.UTC()
	}
	key := occurredAt.Format("2006-01-02")
	bucket := projection.DailyBuckets[key]
	ensureBucketMaps(&bucket)
	switch fact.FactType {
	case FactTypeUserFeedback:
		bucket.FeedbackCount++
		switch strings.TrimSpace(fact.FeedbackType) {
		case "thumbs_up", "useful":
			bucket.PositiveFeedbackCount++
		case "thumbs_down", "irrelevant", "too_frequent":
			bucket.NegativeFeedbackCount++
		case "text":
			bucket.TextFeedbackCount++
		}
		for _, reason := range fact.ReasonCodes {
			bucket.ReasonCodeCounts[reason]++
		}
	case FactTypeServiceScorecard:
		bucket.MetricSampleCounts[fact.MetricID]++
		bucket.MetricScoreSums[fact.MetricID] += fact.MetricValue
		bucket.LatestMetricScores[fact.MetricID] = fact.MetricValue
	}
	projection.DailyBuckets[key] = bucket
}

func learningFactPriority(fact Fact) string {
	if fact.FactType == FactTypeServiceScorecard {
		if fact.MetricID == "safety_compliance" ||
			fact.MetricID == "privacy_comfort" ||
			fact.MetricValue <= 2 {
			return "high"
		}
		if fact.MetricValue <= 3 {
			return "medium"
		}
		return "normal"
	}
	switch strings.TrimSpace(fact.FeedbackType) {
	case "thumbs_down", "irrelevant", "too_frequent", "text":
		return "high"
	}
	for _, reason := range fact.ReasonCodes {
		if reason == "unsafe" || reason == "privacy" {
			return "high"
		}
	}
	if strings.TrimSpace(fact.ActionType) != "" {
		return "medium"
	}
	return "normal"
}

func ensureProjectionMaps(projection *LearningProjection) {
	if projection.MetricSampleCounts == nil {
		projection.MetricSampleCounts = map[string]int64{}
	}
	if projection.MetricScoreSums == nil {
		projection.MetricScoreSums = map[string]float64{}
	}
	if projection.LatestMetricScores == nil {
		projection.LatestMetricScores = map[string]float64{}
	}
	if projection.ReasonCodeCounts == nil {
		projection.ReasonCodeCounts = map[string]int64{}
	}
	if projection.DailyBuckets == nil {
		projection.DailyBuckets = map[string]LearningProjectionBucket{}
	}
}

func ensureBucketMaps(bucket *LearningProjectionBucket) {
	if bucket.MetricSampleCounts == nil {
		bucket.MetricSampleCounts = map[string]int64{}
	}
	if bucket.MetricScoreSums == nil {
		bucket.MetricScoreSums = map[string]float64{}
	}
	if bucket.LatestMetricScores == nil {
		bucket.LatestMetricScores = map[string]float64{}
	}
	if bucket.ReasonCodeCounts == nil {
		bucket.ReasonCodeCounts = map[string]int64{}
	}
}

func SortedProjectionReasonCodes(counts map[string]int64) []string {
	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
