package main

import (
	"bufio"
	"context"
	"encoding/json"
	"encoding/pem"
	"errors"
	"net/http/httptest"
	"os"
	"sync/atomic"

	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type assignmentPublisher struct{}

func (assignmentPublisher) PublishExperimentAssignment(
	context.Context,
	application.AssignmentObservation,
) error {
	return nil
}

type failOnceRecallBackend struct {
	calls atomic.Int32
}

func (backend *failOnceRecallBackend) Recall(
	context.Context,
	rtsearch.RetrievePlan,
) ([]rtsearch.RecallCandidate, error) {
	if backend.calls.Add(1) == 1 {
		return nil, errors.New("injected Elasticsearch unavailable")
	}
	return []rtsearch.RecallCandidate{{
		Document: rtsearch.Document{
			ObjectType:  "content.post",
			ObjectID:    "post-a",
			Title:       "title",
			Summary:     "summary",
			ContentType: "article",
			Visibility:  "public",
		},
		BaseScore: 1,
		Source:    "test",
	}}, nil
}

func (*failOnceRecallBackend) Name() string { return "fail-once-recall" }

func main() {
	experiments, err := application.NewExperiments(assignmentPublisher{})
	if err != nil {
		panic(err)
	}
	if err := experiments.ApplyPolicy(application.ExperimentPolicy{
		ID:       application.SearchRankingExperimentID,
		Revision: 1,
		Status:   "running",
		Variants: []application.ExperimentPolicyVariant{
			{Key: application.BucketControl, AllocationBasisPoints: 5000},
			{Key: application.BucketTermHeat, AllocationBasisPoints: 5000},
		},
		UpdatedAt: "2026-08-28T00:00:00Z",
	}); err != nil {
		panic(err)
	}
	handler := searchhttp.NewHandler(
		application.NewSearchService(&failOnceRecallBackend{}),
		application.NewRankingDecorator(nil, experiments, 0, nil),
		nil,
	).Routes()
	server := httptest.NewTLSServer(handler)
	defer server.Close()

	certificateFile, err := os.CreateTemp("", "qwq-search-retry-ca-*.pem")
	if err != nil {
		panic(err)
	}
	certificatePath := certificateFile.Name()
	defer os.Remove(certificatePath)
	if err := pem.Encode(certificateFile, &pem.Block{
		Type:  "CERTIFICATE",
		Bytes: server.Certificate().Raw,
	}); err != nil {
		panic(err)
	}
	if err := certificateFile.Close(); err != nil {
		panic(err)
	}

	if err := json.NewEncoder(os.Stdout).Encode(map[string]string{
		"baseUrl": server.URL,
		"caFile":  certificatePath,
	}); err != nil {
		panic(err)
	}
	_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
}
