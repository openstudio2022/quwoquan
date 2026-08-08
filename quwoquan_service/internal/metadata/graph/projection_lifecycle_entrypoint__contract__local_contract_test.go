package graph

import (
	"slices"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestProjectionLifecyclePoliciesMatchConsumersAndResolvedEntrypoints(t *testing.T) {
	t.Parallel()

	repoRoot := contractsview.RepositoryRoot(t)
	catalog, err := load.Load(contractsview.Build(t), load.WithRepoRoot(repoRoot))
	if err != nil {
		t.Fatal(err)
	}
	targets := map[string]string{
		"user.following_subject":                             "aggregate_version",
		"user.creator_runtime_profile":                       "event_id",
		"circle.circle_search_item_view":                     "aggregate_version",
		"search.search_index_view":                           "event_id",
		"tag.object_tag_index_view":                          "aggregate_version",
		"recommendation.recommendation_candidate_index_view": "aggregate_version",
	}
	objects := map[string]*ast.Object{}
	for index := range catalog.Objects {
		object := &catalog.Objects[index]
		if _, targeted := targets[object.ID]; targeted {
			objects[object.ID] = object
		}
	}
	for objectID, expectedIdempotency := range targets {
		object := objects[objectID]
		if object == nil || object.Lifecycle == nil ||
			len(object.Lifecycle.EventConsumers) == 0 {
			t.Fatalf("projection lifecycle missing for %s: %+v", objectID, object)
		}
		if strings.TrimSpace(object.Lifecycle.Idempotency) == "" ||
			object.Lifecycle.Idempotency != expectedIdempotency {
			t.Fatalf("%s lifecycle idempotency=%q, want %q",
				objectID, object.Lifecycle.Idempotency, expectedIdempotency)
		}
		for _, consumer := range object.Lifecycle.EventConsumers {
			if consumer.Idempotency != object.Lifecycle.Idempotency {
				t.Fatalf("%s consumer %s idempotency=%q, want lifecycle %q",
					objectID, consumer.Name, consumer.Idempotency,
					object.Lifecycle.Idempotency)
			}
		}
	}

	target := objects["recommendation.recommendation_candidate_index_view"]
	if got := len(target.Lifecycle.EventConsumers); got != 5 {
		t.Fatalf("recommendation projector consumers=%d, want 5", got)
	}
	for _, consumer := range target.Lifecycle.EventConsumers {
		if consumer.Implementation == nil ||
			!evidenceArtifactReady(*consumer.Implementation) {
			t.Fatalf("unresolved recommendation projector consumer: %+v", consumer)
		}
	}
	contractGraph := Build(catalog)
	for _, readiness := range contractGraph.ObjectReadiness {
		if readiness.ObjectID != target.ID {
			continue
		}
		if !readiness.ContractReady ||
			slices.Contains(readiness.Missing, "operation.entrypoint") ||
			slices.Contains(readiness.Missing, "lifecycle.event_consumer") {
			t.Fatalf("resolved projector entrypoints rejected: %+v", readiness)
		}
		return
	}
	t.Fatalf("readiness packet missing for %s", target.ID)
}

func TestNonHTTPProjectionUsesAllTypedLifecycleProjectorsAsEntrypointCoverage(t *testing.T) {
	t.Parallel()

	consumers := []ast.LifecycleEventConsumer{
		projectionConsumer("ProjectPostLifecycle", "PostLifecycleConsumer", "post.go"),
		projectionConsumer("ProjectPremiumPool", "PremiumPoolConsumer", "premium_pool.go"),
		projectionConsumer("ProjectPersonaRelationship", "PersonaRelationshipConsumer", "persona.go"),
		projectionConsumer("ProjectAccountRestriction", "AccountRestrictionConsumer", "account.go"),
		projectionConsumer("ProjectGatheringLifecycle", "GatheringLifecycleConsumer", "gathering.go"),
	}
	readiness := projectionReadiness(consumers, true)

	if !readiness.ContractReady || readiness.Stage != "contract-ready" {
		t.Fatalf("valid lifecycle projector entrypoints rejected: %+v", readiness)
	}
	if slices.Contains(readiness.Missing, "operation.entrypoint") ||
		slices.Contains(readiness.Missing, "lifecycle.event_consumer") {
		t.Fatalf("valid lifecycle projector entrypoints reported missing: %v", readiness.Missing)
	}
}

func TestLifecycleOnlyProjectionStaticEvidenceStopsAtImplemented(t *testing.T) {
	t.Parallel()

	object := projectionObject([]ast.LifecycleEventConsumer{
		projectionConsumer("ProjectPostLifecycle", "PostLifecycleConsumer", "post.go"),
	}, true)
	evidence := completeImplementationEvidence()
	evidence.ObjectID = object.ID
	evidence.Service.Domain = nil
	evidence.Service.Transport = nil
	contractGraph := Build(&ast.Catalog{
		Objects:            []ast.Object{object},
		BusinessObjectMaps: []ast.BusinessObjectMap{mapForObject(object)},
		ReadinessEvidence:  []ast.ObjectReadinessEvidence{evidence},
	})
	readiness := contractGraph.ObjectReadiness[0]
	if readiness.Stage != "implemented" || !readiness.ContractReady ||
		!readiness.Implemented || readiness.CommercialReady {
		t.Fatalf("static lifecycle projection readiness=%+v, want implemented only", readiness)
	}
	if !slices.Equal(readiness.Missing, []string{"commercial.result_bundle"}) {
		t.Fatalf("missing=%v, want only commercial.result_bundle", readiness.Missing)
	}
}

func TestNonHTTPProjectionWithoutLifecycleConsumerRemainsBlocked(t *testing.T) {
	t.Parallel()

	readiness := projectionReadiness(nil, false)
	if readiness.ContractReady || !slices.Contains(readiness.Missing, "operation.entrypoint") {
		t.Fatalf("projection without any entrypoint was accepted: %+v", readiness)
	}
}

func TestNonHTTPProjectionRejectsInvalidLifecycleProjectorCoverage(t *testing.T) {
	t.Parallel()

	tests := map[string]func([]ast.LifecycleEventConsumer) []ast.LifecycleEventConsumer{
		"pseudo implementation digest": func(values []ast.LifecycleEventConsumer) []ast.LifecycleEventConsumer {
			values[0].Implementation.SHA256 = "declared-but-not-derived"
			return values
		},
		"duplicate consumer": func(values []ast.LifecycleEventConsumer) []ast.LifecycleEventConsumer {
			values = append(values, values[0])
			return values
		},
		"missing implementation": func(values []ast.LifecycleEventConsumer) []ast.LifecycleEventConsumer {
			values[0].Implementation = nil
			return values
		},
	}
	for name, mutate := range tests {
		name, mutate := name, mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			consumers := mutate([]ast.LifecycleEventConsumer{
				projectionConsumer("ProjectPostLifecycle", "PostLifecycleConsumer", "post.go"),
			})
			readiness := projectionReadiness(consumers, true)
			if readiness.ContractReady ||
				!slices.Contains(readiness.Missing, "lifecycle.event_consumer") {
				t.Fatalf("invalid lifecycle coverage accepted: %+v", readiness)
			}
		})
	}
}

func TestNonHTTPProjectionRequiresCompleteLifecyclePolicy(t *testing.T) {
	t.Parallel()

	tests := map[string]func(*ast.LifecycleDefinition){
		"checkpoint":  func(value *ast.LifecycleDefinition) { value.Checkpoint = "" },
		"rebuild":     func(value *ast.LifecycleDefinition) { value.Rebuild = "" },
		"tombstone":   func(value *ast.LifecycleDefinition) { value.Tombstone = "" },
		"idempotency": func(value *ast.LifecycleDefinition) { value.Idempotency = "" },
	}
	for name, mutate := range tests {
		name, mutate := name, mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			object := projectionObject([]ast.LifecycleEventConsumer{
				projectionConsumer("ProjectPostLifecycle", "PostLifecycleConsumer", "post.go"),
			}, true)
			mutate(object.Lifecycle)
			readiness := readinessForObject(object)
			if readiness.ContractReady ||
				!slices.Contains(readiness.Missing, "lifecycle.event_consumer") {
				t.Fatalf("projection with incomplete %s accepted: %+v", name, readiness)
			}
		})
	}
}

func TestLifecycleProjectorCoverageDoesNotRelaxOtherObjectKinds(t *testing.T) {
	t.Parallel()

	aggregate := projectionObject([]ast.LifecycleEventConsumer{
		projectionConsumer("HandlePostLifecycle", "PostLifecycleHandler", "post.go"),
	}, true)
	aggregate.Kind = ast.ObjectKindAggregateRoot
	aggregate.Lifecycle.EventConsumers[0].Kind = "event_handler"
	readiness := readinessForObject(aggregate)
	if readiness.ContractReady || !slices.Contains(readiness.Missing, "operation.entrypoint") {
		t.Fatalf("aggregate accepted lifecycle-only projection rule: %+v", readiness)
	}

	runtimeSession := projectionObject(nil, false)
	runtimeSession.Kind = ast.ObjectKindRuntimeSession
	readiness = readinessForObject(runtimeSession)
	if readiness.ContractReady || !slices.Contains(readiness.Missing, "operation.entrypoint") {
		t.Fatalf("runtime session accepted without its middleware entrypoint: %+v", readiness)
	}
}

func projectionReadiness(
	consumers []ast.LifecycleEventConsumer,
	withLifecycle bool,
) ObjectReadiness {
	return readinessForObject(projectionObject(consumers, withLifecycle))
}

func readinessForObject(object ast.Object) ObjectReadiness {
	contractGraph := Build(&ast.Catalog{
		Objects:            []ast.Object{object},
		BusinessObjectMaps: []ast.BusinessObjectMap{mapForObject(object)},
	})
	return contractGraph.ObjectReadiness[0]
}

func mapForObject(object ast.Object) ast.BusinessObjectMap {
	return ast.BusinessObjectMap{
		Domain: object.Domain,
		Objects: []ast.BusinessObjectBoundary{{
			CanonicalObject: object.Name,
		}},
	}
}

func projectionObject(
	consumers []ast.LifecycleEventConsumer,
	withLifecycle bool,
) ast.Object {
	object := ast.Object{
		ID:     "recommendation.recommendation_candidate_index_view",
		Domain: "recommendation", Name: "RecommendationCandidateIndexView",
		Kind: ast.ObjectKindProjection, KindExplicit: true,
	}
	if withLifecycle {
		object.Lifecycle = &ast.LifecycleDefinition{
			SourceEvents:   []string{"content.post.PostPublished"},
			Checkpoint:     "per_source_partition_sequence",
			Rebuild:        "replay_all_source_events",
			Tombstone:      "remove_candidate_keep_checkpoint",
			Idempotency:    "aggregate_version",
			EventConsumers: consumers,
		}
	}
	return object
}

func projectionConsumer(name, facet, path string) ast.LifecycleEventConsumer {
	return ast.LifecycleEventConsumer{
		Name: name, Kind: "projector", Facet: facet,
		Method: "processOnce", Idempotency: "aggregate_version",
		Implementation: &ast.EvidenceArtifact{
			Path: "quwoquan_service/services/recommendation-service/" +
				"internal/recommendation/recommendation_candidate_index_view/adapters/" + path,
			SHA256: strings.Repeat("a", 64),
		},
	}
}
