package local_contract

import (
	"context"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	application "quwoquan_service/services/search-service/internal/search/search_query/application"
	"quwoquan_service/services/search-service/internal/search/search_query/application/queryheat"
)

type migratedTermHeatProvider struct {
	terms []queryheat.TermHeat
}

func (p migratedTermHeatProvider) RelatedTerms(context.Context, string, int) ([]queryheat.TermHeat, error) {
	return p.terms, nil
}

func TestSearchRankingAndTermHeatUseApplicationPorts(t *testing.T) {
	experiments, err := application.NewExperiments(application.ExperimentConfig{
		Enabled: true,
		Buckets: []application.ExperimentBucket{{
			Name:      application.BucketTermHeat,
			WeightPct: 100,
		}},
	})
	if err != nil {
		t.Fatalf("NewExperiments() error = %v", err)
	}
	decorator := application.NewRankingDecorator(
		migratedTermHeatProvider{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 10}}},
		experiments,
		5,
		nil,
	)
	result, err := decorator.Decorate(context.Background(), rtsearch.RetrieveResponse{
		Hits: []rtsearch.RetrieveHit{
			{Target: rtsearch.TargetArticle, ObjectID: "a", Title: "成都美食指南", Score: 2, RankPosition: 1},
			{Target: rtsearch.TargetArticle, ObjectID: "b", Title: "成都火锅攻略", Score: 1, RankPosition: 2},
		},
	}, "成都", "persona-1")
	if err != nil {
		t.Fatalf("Decorate() error = %v", err)
	}
	if result.ExperimentBucket != application.BucketTermHeat ||
		result.Hits[0].ObjectID != "b" || result.Hits[0].RankPosition != 1 {
		t.Fatalf("ranked result = %#v", result)
	}

	now := time.Date(2026, time.June, 16, 0, 0, 0, 0, time.UTC)
	heats := queryheat.Compute([]queryheat.QueryRecord{
		{NormalizedTerm: "recent", CreatedAt: now.Add(-time.Hour)},
		{NormalizedTerm: "old", CreatedAt: now.Add(-240 * time.Hour)},
	}, nil, queryheat.Config{HalfLifeHours: 24, Now: func() time.Time { return now }})
	byTerm := queryheat.HeatByTerm(heats)
	if byTerm["recent"].DecayedHeat <= byTerm["old"].DecayedHeat {
		t.Fatalf("recency decay lost ordering: %#v", heats)
	}
}

func TestSearchRankingExperimentPolicyFailsClosed(t *testing.T) {
	if experiments, err := application.NewExperiments(application.ExperimentConfig{}); err == nil || experiments != nil {
		t.Fatalf("empty NewExperiments() = (%#v, %v), want fail-closed", experiments, err)
	}

	disabled, err := application.NewExperiments(application.ExperimentConfig{
		Enabled: false,
		Buckets: []application.ExperimentBucket{{
			Name:      application.BucketControl,
			WeightPct: 100,
		}},
	})
	if err != nil {
		t.Fatalf("disabled NewExperiments() error = %v", err)
	}
	if bucket, assignErr := disabled.Assign(context.Background(), "persona-1"); assignErr == nil || bucket != "" {
		t.Fatalf("disabled Assign() = (%q, %v), want fail-closed", bucket, assignErr)
	}
}
