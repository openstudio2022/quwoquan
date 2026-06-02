package recommendation

import "quwoquan_service/runtime/recpolicy"

// testPolicyStore builds a policy store from the codegen baseline, optionally
// mutating the policy first. Tests use this instead of hand-coded weight/option
// constants so the single policy source (policy.yaml -> baseline) is exercised.
func testPolicyStore(mutate func(*recpolicy.RecPolicy)) *recpolicy.Store {
	p := recpolicy.Baseline()
	if mutate != nil {
		mutate(p)
	}
	return recpolicy.NewStore(p)
}

// noExplorePolicyStore returns a store whose scorer never injects random
// explore boost, giving deterministic ordering for ranking assertions and
// benchmarks (replaces the former WithExploreFraction(0) option).
func noExplorePolicyStore() *recpolicy.Store {
	return testPolicyStore(func(p *recpolicy.RecPolicy) {
		p.Scorer.ExploreFraction = 0
	})
}
