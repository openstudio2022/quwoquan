package sli

import (
	"context"
	"fmt"
	"math"
	"sort"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// Collector records SLI data points and generates reports.
type Collector struct {
	mu         sync.RWMutex
	indicators map[string]Indicator
	dataColl   *mongo.Collection
	knowledgeColl *mongo.Collection
}

func NewCollector(db *mongo.Database) *Collector {
	return &Collector{
		indicators:    make(map[string]Indicator),
		dataColl:      db.Collection("sli_data_points"),
		knowledgeColl: db.Collection("agent_knowledge"),
	}
}

// RegisterIndicator adds an SLI definition.
func (c *Collector) RegisterIndicator(ind Indicator) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.indicators[ind.ID] = ind
}

// GetIndicator returns an indicator by ID.
func (c *Collector) GetIndicator(id string) (Indicator, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	ind, ok := c.indicators[id]
	return ind, ok
}

// ListIndicators returns all registered indicators.
func (c *Collector) ListIndicators() []Indicator {
	c.mu.RLock()
	defer c.mu.RUnlock()
	result := make([]Indicator, 0, len(c.indicators))
	for _, ind := range c.indicators {
		result = append(result, ind)
	}
	return result
}

// Record persists a data point.
func (c *Collector) Record(ctx context.Context, dp DataPoint) error {
	dp.Timestamp = time.Now().UTC()
	_, err := c.dataColl.InsertOne(ctx, dp)
	return err
}

// RecordBatch persists multiple data points.
func (c *Collector) RecordBatch(ctx context.Context, points []DataPoint) error {
	docs := make([]any, len(points))
	now := time.Now().UTC()
	for i, dp := range points {
		dp.Timestamp = now
		docs[i] = dp
	}
	_, err := c.dataColl.InsertMany(ctx, docs)
	return err
}

// GenerateReport computes a report for the given indicator over the time range.
func (c *Collector) GenerateReport(ctx context.Context, indicatorID string, from, to time.Time) (*Report, error) {
	c.mu.RLock()
	ind, ok := c.indicators[indicatorID]
	c.mu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("indicator %q not registered", indicatorID)
	}

	filter := bson.M{
		"indicatorId": indicatorID,
		"timestamp":   bson.M{"$gte": from, "$lte": to},
	}

	cursor, err := c.dataColl.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "timestamp", Value: 1}}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var points []DataPoint
	if err := cursor.All(ctx, &points); err != nil {
		return nil, err
	}

	summary := computeSummary(points)

	report := &Report{
		IndicatorID: indicatorID,
		Feature:     ind.Feature,
		Entity:      ind.Entity,
		Window:      TimeRange{From: from, To: to},
		Summary:     summary,
		Objective:   ind.Objective,
	}

	if ind.Objective != nil {
		report.Met = evaluateObjective(ind.Objective, summary)
	}

	return report, nil
}

// LearnFromReport persists a knowledge entry derived from a report.
func (c *Collector) LearnFromReport(ctx context.Context, report *Report) error {
	entry := KnowledgeEntry{
		ID:      fmt.Sprintf("%s_%s_%s", report.Feature, report.IndicatorID, report.Window.To.Format("20060102")),
		Feature: report.Feature,
		Entity:  report.Entity,
		Type:    "sli_report",
		Content: fmt.Sprintf("indicator=%s mean=%.4f p95=%.4f met=%v", report.IndicatorID, report.Summary.Mean, report.Summary.P95, report.Met),
		Metrics: map[string]float64{
			"mean":    report.Summary.Mean,
			"p95":     report.Summary.P95,
			"p99":     report.Summary.P99,
			"count":   float64(report.Summary.Count),
			"current": report.Summary.Current,
		},
		LearnedAt: time.Now().UTC(),
		Source:    "sli_collector",
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := c.knowledgeColl.UpdateOne(ctx,
		bson.M{"_id": entry.ID},
		bson.M{"$set": entry},
		opts,
	)
	return err
}

// QueryKnowledge searches the agent knowledge base.
func (c *Collector) QueryKnowledge(ctx context.Context, feature string, limit int) ([]KnowledgeEntry, error) {
	filter := bson.M{}
	if feature != "" {
		filter["feature"] = bson.M{"$regex": feature, "$options": "i"}
	}

	findOpts := options.Find().
		SetSort(bson.D{{Key: "learnedAt", Value: -1}}).
		SetLimit(int64(limit))

	cursor, err := c.knowledgeColl.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var entries []KnowledgeEntry
	if err := cursor.All(ctx, &entries); err != nil {
		return nil, err
	}
	return entries, nil
}

func computeSummary(points []DataPoint) Summary {
	if len(points) == 0 {
		return Summary{}
	}

	values := make([]float64, len(points))
	var sum float64
	minVal := math.MaxFloat64
	maxVal := -math.MaxFloat64

	for i, p := range points {
		values[i] = p.Value
		sum += p.Value
		if p.Value < minVal {
			minVal = p.Value
		}
		if p.Value > maxVal {
			maxVal = p.Value
		}
	}

	sort.Float64s(values)
	n := len(values)

	return Summary{
		Count:   int64(n),
		Sum:     sum,
		Mean:    sum / float64(n),
		P50:     percentile(values, 0.50),
		P95:     percentile(values, 0.95),
		P99:     percentile(values, 0.99),
		Min:     minVal,
		Max:     maxVal,
		Current: values[n-1],
	}
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	idx := p * float64(len(sorted)-1)
	lower := int(idx)
	upper := lower + 1
	if upper >= len(sorted) {
		return sorted[len(sorted)-1]
	}
	frac := idx - float64(lower)
	return sorted[lower]*(1-frac) + sorted[upper]*frac
}

func evaluateObjective(obj *Objective, summary Summary) bool {
	var actual float64
	switch obj.Operator {
	case "<=":
		actual = summary.P95
		return actual <= obj.Target
	case ">=":
		actual = summary.Mean
		return actual >= obj.Target
	case "<":
		actual = summary.P99
		return actual < obj.Target
	case ">":
		actual = summary.Mean
		return actual > obj.Target
	default:
		return summary.Mean >= obj.Target
	}
}
