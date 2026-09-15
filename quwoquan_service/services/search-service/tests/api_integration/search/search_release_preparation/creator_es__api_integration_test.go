package preparation_test

import (
	"context"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/tests/support"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestRealESReleaseCandidatesStageAndFence(t *testing.T) {
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Minute)
	defer cancel()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	client, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "unified_release", RequestTimeout: 5 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	d := "sha256:" + strings.Repeat("a", 64)
	a := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"gamma", "qwq_data", "a", d}, Slice: "creator_search", ProviderBindingGeneration: d, SchemaGeneration: client.SchemaGeneration()}
	b := a
	b.Release.ReleaseID = "b"
	build := func(binding rt.ReleaseQueryPreparationBinding, name string) rt.SearchReleaseCandidateSnapshot {
		creator := rt.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: d, Profiles: []rt.CreatorSearchPublicSnapshot{{ObjectType: "user.profile", ObjectID: "same", PersonaID: "same", CreatorID: "creator", AuthorID: "author", UserHandle: "handle", DisplayName: name, IdentityTags: []string{}, SourceVersion: 1, ProfileDigest: d, UpdatedAt: "2026-09-12T00:00:00Z"}}}
		_ = creator.Seal()
		return rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &creator}
	}
	for _, item := range []struct {
		binding rt.ReleaseQueryPreparationBinding
		name    string
	}{{a, "作者甲"}, {b, "作者乙"}} {
		snapshot := build(item.binding, item.name)
		if _, err = client.WriteReleaseCandidate(ctx, item.binding, snapshot); err != nil {
			t.Fatal(err)
		}
		deadline := time.Now().Add(10 * time.Second)
		for {
			proof, e := client.VerifyReleaseCandidate(ctx, item.binding, snapshot)
			if e == nil {
				if len(proof) != 6 {
					t.Fatal("query classes incomplete")
				}
				break
			}
			if time.Now().After(deadline) {
				t.Fatal(e)
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	for _, want := range []struct {
		binding *rt.ReleaseQueryPreparationBinding
		name    string
	}{{&a, "作者甲"}, {&b, "作者乙"}, {&a, "作者甲"}, {nil, ""}} {
		hits, e := es.NewBackend(client, client.IndexName()).Recall(es.WithReleaseBinding(ctx, want.binding), rt.RetrievePlan{Limit: 20})
		if e != nil {
			t.Fatal(e)
		}
		if want.name == "" {
			if len(hits) != 0 {
				t.Fatal("unfenced leak")
			}
		} else if len(hits) != 1 || hits[0].Document.Title != want.name {
			t.Fatal(hits)
		}
	}
}
