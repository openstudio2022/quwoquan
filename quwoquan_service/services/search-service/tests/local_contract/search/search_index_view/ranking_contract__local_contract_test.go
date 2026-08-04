package local_contract

import (
	"context"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	application "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
)

type migratedTermHeatProvider struct {
	terms []queryheat.TermHeat
}

type assignmentPublisherSpy struct {
	observations []application.AssignmentObservation
}

func (p *assignmentPublisherSpy) PublishExperimentAssignment(_ context.Context, observation application.AssignmentObservation) error {
	p.observations = append(p.observations, observation)
	return nil
}

func searchPolicy(status string, control, termHeat int) application.ExperimentPolicy {
	return application.ExperimentPolicy{
		ID: application.SearchRankingExperimentID, Revision: 3, Status: status,
		Variants: []application.ExperimentPolicyVariant{
			{Key: application.BucketControl, AllocationBasisPoints: control},
			{Key: application.BucketTermHeat, AllocationBasisPoints: termHeat},
		},
		UpdatedAt: "2026-07-31T10:00:00Z",
	}
}

func (p migratedTermHeatProvider) RelatedTerms(context.Context, string, int) ([]queryheat.TermHeat, error) {
	return p.terms, nil
}

func TestSearchRankingAndTermHeatUseApplicationPorts(t *testing.T) {
	publisher := &assignmentPublisherSpy{}
	experiments, err := application.NewExperiments(publisher)
	if err != nil {
		t.Fatalf("NewExperiments() error = %v", err)
	}
	if err := experiments.ApplyPolicy(searchPolicy("running", 1, 9999)); err != nil {
		t.Fatalf("ApplyPolicy() error = %v", err)
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
	if len(publisher.observations) != 1 || publisher.observations[0].ExperimentRevision != 3 {
		t.Fatalf("assignment observations = %#v", publisher.observations)
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
	if experiments, err := application.NewExperiments(nil); err == nil || experiments != nil {
		t.Fatalf("publisher-less NewExperiments() = (%#v, %v), want fail-closed", experiments, err)
	}

	disabled, err := application.NewExperiments(&assignmentPublisherSpy{})
	if err != nil {
		t.Fatalf("disabled NewExperiments() error = %v", err)
	}
	if bucket, assignErr := disabled.Assign(context.Background(), "persona-1"); assignErr == nil || bucket != "" {
		t.Fatalf("unprojected Assign() = (%q, %v), want fail-closed", bucket, assignErr)
	}
	if err := disabled.ApplyPolicy(searchPolicy("paused", 5000, 5000)); err != nil {
		t.Fatalf("paused ApplyPolicy() error = %v", err)
	}
	if bucket, assignErr := disabled.Assign(context.Background(), "persona-1"); assignErr == nil || bucket != "" {
		t.Fatalf("paused Assign() = (%q, %v), want fail-closed", bucket, assignErr)
	}
}


func TestSearchRankingExperimentAssignmentDegradesToControl(t *testing.T) {
	disabled, err := application.NewExperiments(&assignmentPublisherSpy{})
	if err != nil {
		t.Fatalf("NewExperiments() error = %v", err)
	}
	decorator := application.NewRankingDecorator(nil, disabled, 1, nil)
	result, err := decorator.Decorate(context.Background(), rtsearch.RetrieveResponse{
		Hits: []rtsearch.RetrieveHit{{Target: rtsearch.TargetArticle, ObjectID: "a", Title: "x", Score: 1}},
	}, "成都", "persona-1")
	if err != nil {
		t.Fatalf("Decorate() error = %v, want degrade without hard failure", err)
	}
	if result.ExperimentBucket != application.BucketControl {
		t.Fatalf("bucket = %q, want control", result.ExperimentBucket)
	}
}
