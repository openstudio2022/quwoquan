package runruntime

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/url"
	"strings"
	"unicode/utf8"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

const (
	maxDurableCompletionCapsuleBytes      = 512 << 10
	maxDurableCompletionAnswerRunes       = 12000
	maxDurableCompletionProcesses         = 128
	maxDurableCompletionArtifactRefs      = 128
	maxDurableCompletionReferencesPerStep = 5
	maxDurableCompletionIdentifierRunes   = 256
	maxDurableCompletionArtifactRefRunes  = 1024
	maxDurableCompletionSummaryRunes      = 2048
	maxDurableCompletionURLRunes          = 2048
	completionCapsulePayloadKey           = "completionCapsule"
	completionDigestPayloadKey            = "completionDigest"
)

// durableCompletionCapsule contains only the bounded, user-visible result
// accepted by the verifier. Provider diagnostics, reasoning and credentials
// are intentionally not representable as dedicated fields.
type durableCompletionCapsule struct {
	AnswerText   string                                      `json:"answerText"`
	Processes    []assistantmodel.AssistantRunVisibleProcess `json:"processes"`
	Presentation map[string]any                              `json:"presentation,omitempty"`
	ArtifactRefs []string                                    `json:"artifactRefs"`
}

func completionAnswerItemID(runID string) string {
	return "answer:" + strings.TrimSpace(runID)
}

func encodeDurableCompletionCapsule(
	result ExecutionResult,
	availableArtifactRefs []string,
) (durableCompletionCapsule, string, string, error) {
	answer := strings.TrimSpace(result.AnswerText)
	artifactRefs := uniqueSorted(availableArtifactRefs)
	if answer == "" || utf8.RuneCountInString(answer) > maxDurableCompletionAnswerRunes ||
		len(result.Processes) > maxDurableCompletionProcesses ||
		len(artifactRefs) > maxDurableCompletionArtifactRefs {
		return durableCompletionCapsule{}, "", "", ErrUnsafePayload
	}
	for _, artifactRef := range artifactRefs {
		if !boundedCompletionString(artifactRef, maxDurableCompletionArtifactRefRunes, true) {
			return durableCompletionCapsule{}, "", "", ErrUnsafePayload
		}
	}
	processes := make([]assistantmodel.AssistantRunVisibleProcess, len(result.Processes))
	for index := range result.Processes {
		process := result.Processes[index].Clone()
		if process == nil || !validDurableCompletionProcess(*process) {
			return durableCompletionCapsule{}, "", "", ErrUnsafePayload
		}
		processes[index] = *process
	}
	presentation := cloneMap(result.Presentation)
	if len(presentation) > 0 &&
		(!validPresentationDocument(presentation) || unsafeReasoningPayload(presentation)) {
		return durableCompletionCapsule{}, "", "", ErrUnsafePayload
	}
	capsule := durableCompletionCapsule{
		AnswerText:   answer,
		Processes:    processes,
		Presentation: presentation,
		ArtifactRefs: artifactRefs,
	}
	encoded, err := json.Marshal(capsule)
	if err != nil || len(encoded) == 0 || len(encoded) > maxDurableCompletionCapsuleBytes {
		return durableCompletionCapsule{}, "", "", ErrUnsafePayload
	}
	var publicPayload map[string]any
	if err := json.Unmarshal(encoded, &publicPayload); err != nil ||
		unsafeReasoningPayload(publicPayload) ||
		completionPayloadContainsPrivateData(publicPayload) {
		return durableCompletionCapsule{}, "", "", ErrUnsafePayload
	}
	hash := sha256.Sum256(encoded)
	return capsule, string(encoded), "sha256:" + hex.EncodeToString(hash[:]), nil
}

func decodeDurableCompletionCapsule(
	encoded string,
	digest string,
) (durableCompletionCapsule, string, error) {
	if len(encoded) == 0 || len(encoded) > maxDurableCompletionCapsuleBytes ||
		!validCompletionDigest(digest) {
		return durableCompletionCapsule{}, "", ErrJournalCorrupt
	}
	hash := sha256.Sum256([]byte(encoded))
	if "sha256:"+hex.EncodeToString(hash[:]) != strings.TrimSpace(digest) {
		return durableCompletionCapsule{}, "", ErrJournalCorrupt
	}
	var wire durableCompletionCapsule
	if err := json.Unmarshal([]byte(encoded), &wire); err != nil {
		return durableCompletionCapsule{}, "", ErrJournalCorrupt
	}
	normalized, canonical, canonicalDigest, err := encodeDurableCompletionCapsule(
		ExecutionResult{
			AnswerText:   wire.AnswerText,
			Processes:    wire.Processes,
			Presentation: wire.Presentation,
		},
		wire.ArtifactRefs,
	)
	if err != nil || canonical != encoded || canonicalDigest != strings.TrimSpace(digest) {
		return durableCompletionCapsule{}, "", ErrJournalCorrupt
	}
	return normalized, canonicalDigest, nil
}

func completionCapsuleForCurrentAttempt(
	run Run,
) (durableCompletionCapsule, string, error) {
	_, taskAttempt, err := verificationItemIdentity(run)
	if err != nil {
		return durableCompletionCapsule{}, "", err
	}
	answerID := completionAnswerItemID(run.RunID)
	for _, item := range run.Items {
		if item.ItemID != answerID {
			continue
		}
		if item.Kind != generated.AssistantRunItemKindFinalAnswer ||
			item.Status != generated.AssistantRunItemStatusCompleted ||
			item.TaskID != "task_root" ||
			integerPayloadValue(item.Payload["taskAttempt"]) != taskAttempt {
			return durableCompletionCapsule{}, "", ErrJournalCorrupt
		}
		encoded, encodedOK := item.Payload[completionCapsulePayloadKey].(string)
		digest, digestOK := item.Payload[completionDigestPayloadKey].(string)
		if !encodedOK || !digestOK {
			return durableCompletionCapsule{}, "", ErrJournalCorrupt
		}
		capsule, canonicalDigest, decodeErr := decodeDurableCompletionCapsule(
			encoded,
			digest,
		)
		if decodeErr != nil || strings.TrimSpace(stringPayloadValue(
			item.Payload,
			"text",
		)) != capsule.AnswerText ||
			!sameStringSequence(item.ArtifactRefs, capsule.ArtifactRefs) {
			return durableCompletionCapsule{}, "", ErrJournalCorrupt
		}
		return capsule, canonicalDigest, nil
	}
	return durableCompletionCapsule{}, "", ErrJournalCorrupt
}

func validCompletionDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") {
		return false
	}
	raw := strings.TrimPrefix(value, "sha256:")
	return strings.ToLower(raw) == raw && validVerificationFingerprint(raw)
}

func completionPayloadContainsPrivateData(value any) bool {
	forbiddenKeys := map[string]struct{}{
		"authorization": {}, "cookie": {}, "credential": {}, "credentials": {},
		"accesstoken": {}, "refreshtoken": {}, "apikey": {},
		"providerdiagnostic": {}, "providerdiagnostics": {},
		"providerresponse": {}, "rawproviderresponse": {},
	}
	var walk func(any) bool
	walk = func(current any) bool {
		switch typed := current.(type) {
		case map[string]any:
			for key, child := range typed {
				normalized := strings.ToLower(strings.NewReplacer(
					"_", "", "-", "", ".", "",
				).Replace(key))
				if _, found := forbiddenKeys[normalized]; found || walk(child) {
					return true
				}
			}
		case []any:
			for _, child := range typed {
				if walk(child) {
					return true
				}
			}
		case string:
			return stringContainsCredential(typed)
		}
		return false
	}
	return walk(value)
}

func validDurableCompletionProcess(
	process assistantmodel.AssistantRunVisibleProcess,
) bool {
	if !boundedCompletionString(process.ProcessID, maxDurableCompletionIdentifierRunes, true) ||
		!boundedCompletionString(process.Scope, 128, true) ||
		!boundedCompletionString(process.Stage, 128, true) ||
		!boundedCompletionString(process.ActionCode, 128, false) ||
		!boundedCompletionString(process.Status, 128, true) ||
		!boundedCompletionString(process.Summary, maxDurableCompletionSummaryRunes, false) ||
		!boundedCompletionString(process.SkillID, maxDurableCompletionIdentifierRunes, false) ||
		!boundedCompletionString(process.DomainID, maxDurableCompletionIdentifierRunes, false) ||
		process.Order < 0 || process.SearchedDocumentCount < 0 ||
		process.ProcessedDocumentCount < 0 || process.AcceptedDocumentCount < 0 ||
		len(process.AcceptedReferences) > maxDurableCompletionReferencesPerStep {
		return false
	}
	for _, reference := range process.AcceptedReferences {
		if !boundedCompletionString(reference.SourceID, 512, true) ||
			!boundedCompletionString(reference.Title, 512, true) ||
			!boundedCompletionString(reference.Source, 512, false) ||
			!boundedCompletionString(reference.Snippet, maxDurableCompletionSummaryRunes, false) ||
			!boundedCompletionString(reference.Destination.Kind, 128, true) ||
			!boundedCompletionString(reference.Destination.ObjectTypeRef, 512, false) ||
			!boundedCompletionString(reference.Destination.ObjectID, 512, false) ||
			!boundedCompletionString(reference.Destination.URL, maxDurableCompletionURLRunes, false) ||
			!validCompletionDestination(reference.Destination) {
			return false
		}
	}
	return true
}

func validCompletionDestination(destination assistantmodel.CitationDestination) bool {
	if strings.TrimSpace(destination.URL) == "" {
		return strings.TrimSpace(destination.ObjectTypeRef) != "" &&
			strings.TrimSpace(destination.ObjectID) != ""
	}
	parsed, err := url.Parse(strings.TrimSpace(destination.URL))
	return err == nil && parsed.Scheme == "https" && parsed.Host != "" &&
		parsed.User == nil && strings.TrimSpace(destination.ObjectTypeRef) == "" &&
		strings.TrimSpace(destination.ObjectID) == "" &&
		!stringContainsCredential(destination.URL)
}

func boundedCompletionString(value string, maxRunes int, required bool) bool {
	value = strings.TrimSpace(value)
	return (!required || value != "") && utf8.RuneCountInString(value) <= maxRunes
}

func stringContainsCredential(value string) bool {
	trimmed := strings.TrimSpace(value)
	lower := strings.ToLower(trimmed)
	if strings.HasPrefix(lower, "bearer ") || strings.HasPrefix(lower, "basic ") {
		return true
	}
	parsed, err := url.Parse(trimmed)
	if err != nil || (parsed.Scheme != "https" && parsed.Scheme != "http") {
		return false
	}
	if parsed.User != nil {
		return true
	}
	for key := range parsed.Query() {
		normalized := strings.ToLower(strings.NewReplacer(
			"_", "", "-", "", ".", "",
		).Replace(key))
		switch normalized {
		case "token", "accesstoken", "refreshtoken", "apikey", "key",
			"credential", "authorization", "signature", "sig":
			return true
		}
	}
	return false
}
