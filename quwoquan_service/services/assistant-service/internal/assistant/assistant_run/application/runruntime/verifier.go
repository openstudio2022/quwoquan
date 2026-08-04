package runruntime

import "strings"

// VerifyDefinitionOfDone is a deterministic completion gate. A semantic
// verifier may produce the evidence rows, but every frozen requirement must be
// present, passed and backed by at least one artifact before completion.
func VerifyDefinitionOfDone(
	definition DefinitionOfDone,
	evidence []VerificationEvidence,
	availableArtifactRefs []string,
) VerificationVerdict {
	available := make(map[string]struct{}, len(availableArtifactRefs))
	for _, artifactRef := range uniqueSorted(availableArtifactRefs) {
		available[artifactRef] = struct{}{}
	}
	byRequirement := make(map[string]VerificationEvidence, len(evidence))
	duplicates := make(map[string]bool)
	normalizedEvidence := make([]VerificationEvidence, 0, len(evidence))
	for _, item := range evidence {
		key := strings.TrimSpace(item.Requirement)
		if key == "" {
			continue
		}
		item.Requirement = key
		item.ArtifactRefs = uniqueSorted(item.ArtifactRefs)
		item.Summary = strings.TrimSpace(item.Summary)
		if _, exists := byRequirement[key]; exists {
			duplicates[key] = true
		} else {
			byRequirement[key] = item
		}
		normalizedEvidence = append(normalizedEvidence, item)
	}
	verdict := VerificationVerdict{Evidence: normalizedEvidence}
	seenRequirements := map[string]struct{}{}
	for _, requirement := range definition.VerificationRequirements {
		requirement = strings.TrimSpace(requirement)
		if requirement == "" {
			verdict.Missing = append(verdict.Missing, "<empty_requirement>")
			continue
		}
		if _, duplicateRequirement := seenRequirements[requirement]; duplicateRequirement {
			verdict.Failed = append(verdict.Failed, requirement)
			continue
		}
		seenRequirements[requirement] = struct{}{}
		item, ok := byRequirement[requirement]
		if !ok {
			verdict.Missing = append(verdict.Missing, requirement)
			continue
		}
		if duplicates[requirement] || !item.Passed ||
			!allArtifactsAvailable(item.ArtifactRefs, available) {
			verdict.Failed = append(verdict.Failed, requirement)
		}
	}
	verdict.Missing = uniqueSorted(verdict.Missing)
	verdict.Failed = uniqueSorted(verdict.Failed)
	verdict.Accepted = len(verdict.Missing) == 0 && len(verdict.Failed) == 0
	if verdict.Accepted {
		verdict.DecisionSummary = "Definition of Done verified with artifact-backed evidence"
	} else {
		verdict.DecisionSummary = "Definition of Done remains unmet"
	}
	return verdict
}

func allArtifactsAvailable(
	artifactRefs []string,
	available map[string]struct{},
) bool {
	if len(artifactRefs) == 0 {
		return false
	}
	for _, artifactRef := range artifactRefs {
		if _, ok := available[artifactRef]; !ok {
			return false
		}
	}
	return true
}
