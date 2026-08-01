package runruntime

import "strings"

// VerifyDefinitionOfDone is a deterministic completion gate. A semantic
// verifier may produce the evidence rows, but every frozen requirement must be
// present, passed and backed by at least one artifact before completion.
func VerifyDefinitionOfDone(
	definition DefinitionOfDone,
	evidence []VerificationEvidence,
) VerificationVerdict {
	byRequirement := make(map[string]VerificationEvidence, len(evidence))
	for _, item := range evidence {
		key := strings.TrimSpace(item.Requirement)
		if key != "" {
			byRequirement[key] = item
		}
	}
	verdict := VerificationVerdict{Evidence: append([]VerificationEvidence{}, evidence...)}
	for _, requirement := range definition.VerificationRequirements {
		requirement = strings.TrimSpace(requirement)
		item, ok := byRequirement[requirement]
		if !ok {
			verdict.Missing = append(verdict.Missing, requirement)
			continue
		}
		if !item.Passed || len(uniqueSorted(item.EvidenceRefs)) == 0 {
			verdict.Failed = append(verdict.Failed, requirement)
		}
	}
	verdict.Accepted = len(verdict.Missing) == 0 && len(verdict.Failed) == 0
	if verdict.Accepted {
		verdict.DecisionSummary = "Definition of Done verified with artifact-backed evidence"
	} else {
		verdict.DecisionSummary = "Definition of Done remains unmet"
	}
	return verdict
}
