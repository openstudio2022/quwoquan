// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/planner-aggregation-orchestration/spec.md#gwt-004
package assistant_run_test

import (
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/retrievalplan"
)

const testSHA256 = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestRetrievalPlanFreezesExecutionIdentityAndRejectsSilentMutation(t *testing.T) {
	plan, err := retrievalplan.Freeze(retrievalplan.Input{
		Goal: "规划杭州周末亲子露营",
		Queries: []retrievalplan.Query{
			{Dimension: "place", Query: "杭州 亲子 露营 地点", ObjectTypes: []string{"location.place"}, Limit: 10},
			{Dimension: "content", Query: "杭州 亲子 露营 攻略", ObjectTypes: []string{"content.post"}, Limit: 8},
		},
		EvidenceCriteria: []string{"至少一个地点事实", "至少一个可引用攻略"},
		MaximumQueries:   2,
		Identity: retrievalplan.Identity{
			RunID:               "run_01",
			TurnID:              "atn_01",
			ToolName:            "app_search",
			ToolCatalogDigest:   testSHA256,
			AccessPolicyDigest:  testSHA256,
			CandidateDigest:     testSHA256,
			ContractGraphDigest: testSHA256,
			MaximumToolCalls:    4,
		},
	})
	if err != nil {
		t.Fatalf("freeze retrieval plan: %v", err)
	}
	if !strings.HasPrefix(plan.Digest, "sha256:") || len(plan.Digest) != 71 {
		t.Fatalf("digest=%q", plan.Digest)
	}
	if err := plan.Validate(); err != nil {
		t.Fatalf("validate frozen plan: %v", err)
	}

	plan.Queries[0].Query = "执行后偷偷改写"
	if err := plan.Validate(); err == nil || !strings.Contains(err.Error(), "digest") {
		t.Fatalf("mutated plan must fail digest validation: %v", err)
	}
}

func TestRetrievalPlanRejectsHiddenFanoutAndUnboundIdentity(t *testing.T) {
	_, err := retrievalplan.Freeze(retrievalplan.Input{
		Goal: "杭州露营",
		Queries: []retrievalplan.Query{
			{Dimension: "place", Query: "杭州露营地", Limit: 10},
			{Dimension: "content", Query: "杭州露营攻略", Limit: 10},
		},
		EvidenceCriteria: []string{"可引用结果"},
		MaximumQueries:   1,
		Identity: retrievalplan.Identity{
			RunID: "run_01", TurnID: "atn_01", ToolName: "app_search",
			ToolCatalogDigest: testSHA256, AccessPolicyDigest: testSHA256,
			CandidateDigest: testSHA256, ContractGraphDigest: testSHA256,
			MaximumToolCalls: 4,
		},
	})
	if err == nil || !strings.Contains(err.Error(), "maximumQueries") {
		t.Fatalf("hidden fanout must fail: %v", err)
	}

	_, err = retrievalplan.Freeze(retrievalplan.Input{
		Goal:             "杭州露营",
		Queries:          []retrievalplan.Query{{Dimension: "place", Query: "杭州露营地", Limit: 10}},
		EvidenceCriteria: []string{"可引用结果"},
		MaximumQueries:   1,
		Identity: retrievalplan.Identity{
			RunID: "run_01", TurnID: "atn_01", ToolName: "app_search",
			ToolCatalogDigest: testSHA256, AccessPolicyDigest: testSHA256,
			ContractGraphDigest: testSHA256, MaximumToolCalls: 4,
		},
	})
	if err == nil || !strings.Contains(err.Error(), "candidateDigest") {
		t.Fatalf("unbound candidate must fail: %v", err)
	}
}
