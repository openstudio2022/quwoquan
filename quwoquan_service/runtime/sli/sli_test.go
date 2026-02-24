package sli

import (
	"math"
	"testing"
)

func TestComputeSummary(t *testing.T) {
	points := []DataPoint{
		{Value: 10},
		{Value: 20},
		{Value: 30},
		{Value: 40},
		{Value: 50},
	}

	s := computeSummary(points)

	if s.Count != 5 {
		t.Errorf("count: got %d, want 5", s.Count)
	}
	if s.Sum != 150 {
		t.Errorf("sum: got %f, want 150", s.Sum)
	}
	if s.Mean != 30 {
		t.Errorf("mean: got %f, want 30", s.Mean)
	}
	if s.Min != 10 {
		t.Errorf("min: got %f, want 10", s.Min)
	}
	if s.Max != 50 {
		t.Errorf("max: got %f, want 50", s.Max)
	}
	if s.Current != 50 {
		t.Errorf("current: got %f, want 50", s.Current)
	}
}

func TestComputeSummary_Empty(t *testing.T) {
	s := computeSummary(nil)
	if s.Count != 0 {
		t.Errorf("empty count: got %d, want 0", s.Count)
	}
}

func TestPercentile(t *testing.T) {
	sorted := []float64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}

	p50 := percentile(sorted, 0.5)
	if math.Abs(p50-5.5) > 0.01 {
		t.Errorf("p50: got %f, want ~5.5", p50)
	}

	p95 := percentile(sorted, 0.95)
	if p95 < 9.0 {
		t.Errorf("p95: got %f, want >= 9.0", p95)
	}

	p99 := percentile(sorted, 0.99)
	if p99 < 9.5 {
		t.Errorf("p99: got %f, want >= 9.5", p99)
	}
}

func TestEvaluateObjective_LessThanOrEqual(t *testing.T) {
	obj := &Objective{Target: 200, Operator: "<="}
	s := Summary{P95: 150}
	if !evaluateObjective(obj, s) {
		t.Error("150 <= 200 should pass")
	}

	s.P95 = 250
	if evaluateObjective(obj, s) {
		t.Error("250 <= 200 should fail")
	}
}

func TestEvaluateObjective_GreaterThanOrEqual(t *testing.T) {
	obj := &Objective{Target: 0.95, Operator: ">="}
	s := Summary{Mean: 0.97}
	if !evaluateObjective(obj, s) {
		t.Error("0.97 >= 0.95 should pass")
	}

	s.Mean = 0.90
	if evaluateObjective(obj, s) {
		t.Error("0.90 >= 0.95 should fail")
	}
}

func TestRegisterAndListIndicators(t *testing.T) {
	c := &Collector{indicators: make(map[string]Indicator)}

	c.RegisterIndicator(Indicator{
		ID: "rec_ctr", Name: "推荐CTR", Entity: "post", Feature: "feed-recommendation",
		MetricType: MetricRatio, Unit: "%",
		Objective: &Objective{Target: 0.05, Operator: ">="},
	})
	c.RegisterIndicator(Indicator{
		ID: "assistant_satisfaction", Name: "助手满意度", Entity: "assistant_run",
		Feature: "assistant-qa", MetricType: MetricGauge, Unit: "score",
	})

	list := c.ListIndicators()
	if len(list) != 2 {
		t.Errorf("expected 2 indicators, got %d", len(list))
	}

	ind, ok := c.GetIndicator("rec_ctr")
	if !ok {
		t.Fatal("rec_ctr not found")
	}
	if ind.Name != "推荐CTR" {
		t.Errorf("name: got %q, want 推荐CTR", ind.Name)
	}

	_, ok = c.GetIndicator("nonexistent")
	if ok {
		t.Error("nonexistent should not be found")
	}
}

func TestKnowledgeEntryFormat(t *testing.T) {
	entry := KnowledgeEntry{
		ID:      "test_entry",
		Feature: "feed-recommendation",
		Type:    "sli_report",
		Metrics: map[string]float64{"mean": 0.05, "p95": 0.08},
	}
	if entry.Metrics["mean"] != 0.05 {
		t.Errorf("mean: got %f, want 0.05", entry.Metrics["mean"])
	}
}
