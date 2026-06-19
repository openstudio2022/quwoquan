package application

import (
	"context"

	runtimeexperiments "quwoquan_service/runtime/experiments"
)

// SearchRankingExperimentID is the stable AB experiment id for search ranking.
// control = base CrossTypeRanker order; term_heat = search-term heat re-rank on.
const SearchRankingExperimentID = "search_ranking"

const (
	// BucketControl leaves the base ranking untouched (no search-term heat boost).
	BucketControl = "control"
	// BucketTermHeat applies the search-term heat boost so user search terms
	// participate in ranking; AB attribution compares it against control.
	BucketTermHeat = "term_heat"
)

// ExperimentBucket is one AB arm with its rollout weight.
type ExperimentBucket struct {
	Name      string
	WeightPct int
}

// ExperimentConfig is the rollout configuration for the search ranking AB. It is
// supplied by the deploy/config layer (single source per env) and consumed here;
// the bucket NAMES + the experimentBucket response field are the frozen contract.
type ExperimentConfig struct {
	Enabled       bool
	PolicyVersion string
	Buckets       []ExperimentBucket
}

// Experiments deterministically buckets a subject into the search ranking AB,
// reusing the canonical FNV hash resolver (single hashing impl across services).
type Experiments struct {
	resolver *runtimeexperiments.HashResolver
}

// NewExperiments builds the resolver from config. An empty/zero config defaults
// to an enabled 50/50 control vs term_heat split so AB attribution is always on.
func NewExperiments(cfg ExperimentConfig) *Experiments {
	buckets := make([]runtimeexperiments.BucketDef, 0, len(cfg.Buckets))
	for _, b := range cfg.Buckets {
		if b.Name == "" || b.WeightPct <= 0 {
			continue
		}
		buckets = append(buckets, runtimeexperiments.BucketDef{Name: b.Name, WeightPct: b.WeightPct})
	}
	enabled := cfg.Enabled
	policyVersion := cfg.PolicyVersion
	if len(buckets) == 0 {
		buckets = []runtimeexperiments.BucketDef{
			{Name: BucketControl, WeightPct: 50},
			{Name: BucketTermHeat, WeightPct: 50},
		}
		enabled = true
	}
	if policyVersion == "" {
		policyVersion = RankingVersion
	}
	resolver := runtimeexperiments.NewHashResolver()
	resolver.Register(&runtimeexperiments.Experiment{
		ID:            SearchRankingExperimentID,
		Buckets:       buckets,
		PolicyVersion: policyVersion,
		Enabled:       enabled,
	})
	return &Experiments{resolver: resolver}
}

// Assign returns the deterministic bucket for subjectKey. subjectKey must be a
// stable identity (viewerId when logged in, else session id) so a user gets a
// sticky treatment. An empty subjectKey (identity-less anonymous) is forced to
// control: it must never be hashed (a per-request key would re-roll the arm and
// make the same query jump), and identity-less traffic should not silently enter
// the treatment arm. A nil receiver also yields control (safe default).
func (e *Experiments) Assign(ctx context.Context, subjectKey string) string {
	if e == nil || e.resolver == nil || subjectKey == "" {
		return BucketControl
	}
	assignment, err := e.resolver.Resolve(ctx, SearchRankingExperimentID, subjectKey)
	if err != nil || assignment.Bucket == "" {
		return BucketControl
	}
	return assignment.Bucket
}
