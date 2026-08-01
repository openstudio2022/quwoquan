package publicweb

import "strings"

func AssessSearchEvidence(reliable bool, sourceIDs []string) EvidenceAssessment {
	sourceIDs = nonEmptyUnique(sourceIDs)
	if !reliable || len(sourceIDs) == 0 {
		return EvidenceAssessment{
			Status:             EvidenceInsufficient,
			EvidenceSufficient: false,
			ReplanRequired:     true,
			Reason:             "search_sources_unavailable",
			TargetIDs:          []string{},
			DocumentIDs:        []string{},
			ArtifactRefs:       []string{},
			SourceIDs:          sourceIDs,
		}
	}
	// Search results establish authoritative discovery identities, but snippets
	// are not fetched evidence. A durable planner must open a source before
	// treating its facts as verified.
	return EvidenceAssessment{
		Status:             EvidenceInsufficient,
		EvidenceSufficient: false,
		ReplanRequired:     true,
		Reason:             "open_authoritative_source",
		TargetIDs:          []string{},
		DocumentIDs:        []string{},
		ArtifactRefs:       []string{},
		SourceIDs:          sourceIDs,
	}
}

func AssessOpenEvidence(document Document) EvidenceAssessment {
	assessment := EvidenceAssessment{
		Status:       EvidenceAccepted,
		Reason:       "document_evidence_available",
		TargetIDs:    nonEmptyUnique([]string{document.TargetID}),
		DocumentIDs:  nonEmptyUnique([]string{document.DocumentID}),
		ArtifactRefs: nonEmptyUnique([]string{document.ArtifactRef}),
		SourceIDs:    nonEmptyUnique([]string{document.Source.SourceID}),
	}
	assessment.EvidenceSufficient = strings.TrimSpace(document.ContentText) != "" &&
		len(assessment.TargetIDs) == 1 &&
		len(assessment.DocumentIDs) == 1 &&
		len(assessment.ArtifactRefs) == 1 &&
		len(assessment.SourceIDs) == 1
	assessment.ReplanRequired = !assessment.EvidenceSufficient
	if !assessment.EvidenceSufficient {
		assessment.Status = EvidenceInsufficient
		assessment.Reason = "document_evidence_empty_or_incomplete"
	}
	return assessment
}

func AssessFindEvidence(result FindResult) EvidenceAssessment {
	assessment := EvidenceAssessment{
		Status:       EvidenceAccepted,
		Reason:       "document_pattern_matched",
		TargetIDs:    []string{},
		DocumentIDs:  nonEmptyUnique([]string{result.DocumentID}),
		ArtifactRefs: nonEmptyUnique([]string{result.ArtifactRef}),
		SourceIDs:    nonEmptyUnique([]string{result.SourceID}),
	}
	assessment.EvidenceSufficient = len(result.Matches) > 0 &&
		len(assessment.DocumentIDs) == 1 &&
		len(assessment.ArtifactRefs) == 1 &&
		len(assessment.SourceIDs) == 1
	assessment.ReplanRequired = !assessment.EvidenceSufficient
	if !assessment.EvidenceSufficient {
		assessment.Status = EvidenceInsufficient
		if len(result.Matches) == 0 {
			assessment.Reason = "document_pattern_not_found"
		} else {
			assessment.Reason = "document_artifact_unavailable"
		}
	}
	return assessment
}

func nonEmptyUnique(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}
