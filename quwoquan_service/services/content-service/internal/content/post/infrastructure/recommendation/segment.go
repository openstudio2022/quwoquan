package recommendation

import (
	"fmt"
	"os"
	"sort"

	"gopkg.in/yaml.v3"
)

// SegmentMatch is the structured predicate (AND semantics) for one segment.
type SegmentMatch struct {
	LifecycleStages []string             `yaml:"lifecycle_stages"`
	MinTagScores    []SegmentTagScoreReq `yaml:"min_tag_scores"`
}

// SegmentTagScoreReq requires a (tagRef[,dimension]) interest with score>=Min.
type SegmentTagScoreReq struct {
	TagRef    string  `yaml:"tagRef"`
	Dimension string  `yaml:"dimension"`
	Min       float64 `yaml:"min"`
}

// SegmentDef is a rule-based population segment loaded from segments.yaml (SSOT).
type SegmentDef struct {
	ID          string       `yaml:"id"`
	Name        string       `yaml:"name"`
	Description string       `yaml:"description"`
	Priority    int          `yaml:"priority"`
	Match       SegmentMatch `yaml:"match"`
}

// LoadSegments reads the content-owned recommendation segment resource.
func LoadSegments(path string) ([]SegmentDef, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read segments %s: %w", path, err)
	}
	var doc struct {
		Segments []SegmentDef `yaml:"segments"`
	}
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return nil, fmt.Errorf("parse segments %s: %w", path, err)
	}
	return doc.Segments, nil
}

// MatchSegments returns the ids of every segment whose predicate the profile
// satisfies, ordered by descending priority. Pure function. A segment with no
// conditions never matches (no accidental catch-all).
func MatchSegments(profile InterestProfile, defs []SegmentDef) []string {
	sorted := append([]SegmentDef(nil), defs...)
	sort.SliceStable(sorted, func(i, j int) bool {
		if sorted[i].Priority != sorted[j].Priority {
			return sorted[i].Priority > sorted[j].Priority
		}
		return sorted[i].ID < sorted[j].ID
	})
	hit := make([]string, 0, len(sorted))
	for _, d := range sorted {
		if segmentMatches(profile, d.Match) {
			hit = append(hit, d.ID)
		}
	}
	return hit
}

func segmentMatches(p InterestProfile, m SegmentMatch) bool {
	if len(m.LifecycleStages) == 0 && len(m.MinTagScores) == 0 {
		return false
	}
	if len(m.LifecycleStages) > 0 {
		ok := false
		for _, s := range m.LifecycleStages {
			if LifecycleStage(s) == p.LifecycleStage {
				ok = true
				break
			}
		}
		if !ok {
			return false
		}
	}
	for _, req := range m.MinTagScores {
		if !hasInterestAtLeast(p, req) {
			return false
		}
	}
	return true
}

func hasInterestAtLeast(p InterestProfile, req SegmentTagScoreReq) bool {
	for _, ti := range p.TopInterests {
		if ti.TagRef != req.TagRef {
			continue
		}
		if req.Dimension != "" && string(ti.Dimension) != req.Dimension {
			continue
		}
		if ti.Score >= req.Min {
			return true
		}
	}
	return false
}
