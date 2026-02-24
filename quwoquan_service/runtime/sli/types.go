package sli

import "time"

// Indicator defines an SLI metric bound to a specific entity or feature.
type Indicator struct {
	ID          string          `yaml:"id"          json:"id"        bson:"id"`
	Name        string          `yaml:"name"        json:"name"      bson:"name"`
	Entity      string          `yaml:"entity"      json:"entity"    bson:"entity"`
	Feature     string          `yaml:"feature"     json:"feature"   bson:"feature"`
	MetricType  MetricType      `yaml:"metric_type" json:"metricType" bson:"metricType"`
	Unit        string          `yaml:"unit"        json:"unit"      bson:"unit"`
	Objective   *Objective      `yaml:"objective"   json:"objective,omitempty" bson:"objective,omitempty"`
	Tags        []string        `yaml:"tags"        json:"tags"      bson:"tags"`
}

type MetricType string

const (
	MetricCounter   MetricType = "counter"
	MetricGauge     MetricType = "gauge"
	MetricHistogram MetricType = "histogram"
	MetricRatio     MetricType = "ratio"
)

// Objective is the SLO target for this indicator.
type Objective struct {
	Target    float64 `yaml:"target"    json:"target"    bson:"target"`
	Window    string  `yaml:"window"    json:"window"    bson:"window"`
	Operator  string  `yaml:"operator"  json:"operator"  bson:"operator"`
}

// DataPoint is a single measurement.
type DataPoint struct {
	IndicatorID string    `json:"indicatorId" bson:"indicatorId"`
	Value       float64   `json:"value"       bson:"value"`
	Labels      map[string]string `json:"labels" bson:"labels"`
	Timestamp   time.Time `json:"timestamp"   bson:"timestamp"`
}

// Report aggregates indicator data over a time window.
type Report struct {
	IndicatorID string    `json:"indicatorId"`
	Feature     string    `json:"feature"`
	Entity      string    `json:"entity"`
	Window      TimeRange `json:"window"`
	Summary     Summary   `json:"summary"`
	Objective   *Objective `json:"objective,omitempty"`
	Met         bool      `json:"met"`
}

type TimeRange struct {
	From time.Time `json:"from"`
	To   time.Time `json:"to"`
}

type Summary struct {
	Count   int64   `json:"count"`
	Sum     float64 `json:"sum"`
	Mean    float64 `json:"mean"`
	P50     float64 `json:"p50"`
	P95     float64 `json:"p95"`
	P99     float64 `json:"p99"`
	Min     float64 `json:"min"`
	Max     float64 `json:"max"`
	Current float64 `json:"current"`
}

// KnowledgeEntry is a record in the agent decision knowledge base.
type KnowledgeEntry struct {
	ID          string    `json:"id"          bson:"_id"`
	Feature     string    `json:"feature"     bson:"feature"`
	Entity      string    `json:"entity"      bson:"entity"`
	Type        string    `json:"type"        bson:"type"`
	Content     string    `json:"content"     bson:"content"`
	Metrics     map[string]float64 `json:"metrics" bson:"metrics"`
	LearnedAt   time.Time `json:"learnedAt"   bson:"learnedAt"`
	Source      string    `json:"source"      bson:"source"`
}
