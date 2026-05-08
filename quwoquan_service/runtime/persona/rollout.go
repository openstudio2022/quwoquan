package personarollout

import (
	"encoding/json"
	"regexp"
	"sort"
	"strings"
)

const (
	PatchPersonaActivated      = "persona.activated"
	PatchPersonaProfileUpdated = "persona.profile.updated"
	PatchPersonaRetired        = "persona.retired"

	MetricPersonaSwitchLatencyMs          = "persona_switch_latency_ms"
	MetricPersonaAttributionMismatchCount = "persona_attribution_mismatch_count"
	MetricPersonaPublicLeakageCount       = "persona_public_leakage_count"
	MetricPersonaMigrationFailedCount     = "persona_migration_failed_count"
)

var nonHandleChars = regexp.MustCompile(`[^a-z0-9._]+`)

type Input struct {
	Personas        []CurrentPersona `json:"personas"`
	ReservedHandles []string         `json:"reservedHandles,omitempty"`
	PublicSamples   []PublicSample   `json:"publicSamples,omitempty"`
}

type CurrentPersona struct {
	UserID            string   `json:"userId"`
	PersonaID         string   `json:"subAccountId"`
	Username          string   `json:"username,omitempty"`
	Nickname          string   `json:"nickname,omitempty"`
	Phone             string   `json:"phone,omitempty"`
	Email             string   `json:"email,omitempty"`
	IsPrimary         bool     `json:"isPrimary,omitempty"`
	ContentSubjectIDs []string `json:"contentSubjectIds,omitempty"`
	MessageSubjectIDs []string `json:"messageSubjectIds,omitempty"`
	FollowSubjectIDs  []string `json:"followSubjectIds,omitempty"`
}

type PublicSample struct {
	Surface string         `json:"surface"`
	Payload map[string]any `json:"payload"`
}

type Plan struct {
	Personas   []PlannedPersona `json:"personas"`
	Conflicts  []HandleConflict `json:"conflicts"`
	PatchTypes []string         `json:"patchTypes"`
}

type PlannedPersona struct {
	UserID          string              `json:"userId"`
	PersonaID       string              `json:"subAccountId"`
	UserHandle      string              `json:"userHandle"`
	DisplayName     string              `json:"displayName"`
	Phone           string              `json:"phone,omitempty"`
	Email           string              `json:"email,omitempty"`
	IsPrimary       bool                `json:"isPrimary"`
	HistoryMappings map[string][]string `json:"historyMappings"`
	SourceFields    map[string]string   `json:"sourceFields"`
}

type HandleConflict struct {
	PersonaID      string `json:"subAccountId"`
	Requested      string `json:"requested"`
	Assigned       string `json:"assigned"`
	ResolutionRule string `json:"resolutionRule"`
}

type ValidationReport struct {
	Findings                        []ValidationFinding `json:"findings"`
	FailedPersonaIDs                []string            `json:"failedPersonaIds"`
	PersonaMigrationFailedCount     int                 `json:"personaMigrationFailedCount"`
	PersonaAttributionMismatchCount int                 `json:"personaAttributionMismatchCount"`
	PersonaPublicLeakageCount       int                 `json:"personaPublicLeakageCount"`
}

type ValidationFinding struct {
	Code      string `json:"code"`
	PersonaID string `json:"subAccountId,omitempty"`
	Surface   string `json:"surface,omitempty"`
	Message   string `json:"message"`
}

func BuildMigrationPlan(input Input) Plan {
	reserved := make(map[string]struct{}, len(input.ReservedHandles))
	for _, handle := range input.ReservedHandles {
		if normalized := normalizeHandle(handle); normalized != "" {
			reserved[normalized] = struct{}{}
		}
	}

	primaryContacts := buildPrimaryContacts(input.Personas)
	conflicts := make([]HandleConflict, 0)
	planned := make([]PlannedPersona, 0, len(input.Personas))
	for _, persona := range input.Personas {
		requested := requestedHandle(persona)
		assigned := requested
		if assigned == "" {
			assigned = normalizeHandle(persona.PersonaID)
		}
		if _, exists := reserved[assigned]; exists {
			unique := dedupeHandle(assigned, persona.PersonaID, reserved)
			conflicts = append(conflicts, HandleConflict{
				PersonaID:      persona.PersonaID,
				Requested:      assigned,
				Assigned:       unique,
				ResolutionRule: "append persona suffix for global uniqueness",
			})
			assigned = unique
		}
		reserved[assigned] = struct{}{}

		phone := strings.TrimSpace(persona.Phone)
		email := strings.TrimSpace(persona.Email)
		if contacts, ok := primaryContacts[persona.UserID]; ok {
			if phone == "" {
				phone = contacts.Phone
			}
			if email == "" {
				email = contacts.Email
			}
		}

		displayName := strings.TrimSpace(persona.Nickname)
		if displayName == "" {
			displayName = strings.TrimSpace(persona.Username)
		}
		if displayName == "" {
			displayName = strings.TrimSpace(persona.PersonaID)
		}

		planned = append(planned, PlannedPersona{
			UserID:      strings.TrimSpace(persona.UserID),
			PersonaID:   strings.TrimSpace(persona.PersonaID),
			UserHandle:  assigned,
			DisplayName: displayName,
			Phone:       phone,
			Email:       email,
			IsPrimary:   persona.IsPrimary,
			HistoryMappings: map[string][]string{
				"content": cloneStrings(persona.ContentSubjectIDs),
				"message": cloneStrings(persona.MessageSubjectIDs),
				"follow":  cloneStrings(persona.FollowSubjectIDs),
			},
			SourceFields: map[string]string{
				"userHandle": "username|nickname|subAccountId",
				"phone":      "persona.phone|primary.phone",
				"email":      "persona.email|primary.email",
			},
		})
	}

	sort.Slice(planned, func(i, j int) bool {
		if planned[i].UserID == planned[j].UserID {
			if planned[i].IsPrimary != planned[j].IsPrimary {
				return planned[i].IsPrimary
			}
			return planned[i].PersonaID < planned[j].PersonaID
		}
		return planned[i].UserID < planned[j].UserID
	})

	return Plan{
		Personas:   planned,
		Conflicts:  conflicts,
		PatchTypes: []string{PatchPersonaActivated, PatchPersonaProfileUpdated, PatchPersonaRetired},
	}
}

func ValidatePlan(plan Plan, input Input) ValidationReport {
	findings := make([]ValidationFinding, 0)
	failed := make([]string, 0)
	handles := make(map[string]string, len(plan.Personas))
	for _, persona := range plan.Personas {
		if strings.TrimSpace(persona.UserID) == "" || strings.TrimSpace(persona.PersonaID) == "" {
			findings = append(findings, ValidationFinding{
				Code:      "missing_identity",
				PersonaID: persona.PersonaID,
				Message:   "userId 或 subAccountId 为空，无法执行迁移",
			})
			failed = append(failed, persona.PersonaID)
		}
		if prior, exists := handles[persona.UserHandle]; exists {
			findings = append(findings, ValidationFinding{
				Code:      "duplicate_handle",
				PersonaID: persona.PersonaID,
				Message:   "userHandle 与其它分身冲突: " + prior,
			})
			failed = append(failed, persona.PersonaID)
		} else if persona.UserHandle != "" {
			handles[persona.UserHandle] = persona.PersonaID
		}
		attributionMismatch := countBlank(persona.HistoryMappings["content"]) +
			countBlank(persona.HistoryMappings["message"]) +
			countBlank(persona.HistoryMappings["follow"])
		if attributionMismatch > 0 {
			findings = append(findings, ValidationFinding{
				Code:      "history_mapping_gap",
				PersonaID: persona.PersonaID,
				Message:   "存在空白记录主体映射，需人工补齐",
			})
		}
	}

	publicLeakageCount := 0
	for _, sample := range input.PublicSamples {
		for _, key := range []string{"ownerUserId", "ownerAccountId", "ownerId"} {
			if value := strings.TrimSpace(anyString(sample.Payload[key])); value != "" {
				publicLeakageCount++
				findings = append(findings, ValidationFinding{
					Code:    "public_leakage",
					Surface: strings.TrimSpace(sample.Surface),
					Message: "公开读样本包含不允许暴露字段: " + key,
				})
			}
		}
	}

	report := ValidationReport{
		Findings:                        findings,
		FailedPersonaIDs:                dedupeStrings(failed),
		PersonaMigrationFailedCount:     len(dedupeStrings(failed)),
		PersonaAttributionMismatchCount: countFindings(findings, "history_mapping_gap"),
		PersonaPublicLeakageCount:       publicLeakageCount,
	}
	return report
}

func BuildAcceptanceMetrics(switchLatencyMs float64, report ValidationReport) map[string]float64 {
	if switchLatencyMs <= 0 {
		switchLatencyMs = 0
	}
	return map[string]float64{
		MetricPersonaSwitchLatencyMs:          switchLatencyMs,
		MetricPersonaAttributionMismatchCount: float64(report.PersonaAttributionMismatchCount),
		MetricPersonaPublicLeakageCount:       float64(report.PersonaPublicLeakageCount),
		MetricPersonaMigrationFailedCount:     float64(report.PersonaMigrationFailedCount),
	}
}

func BuildReport(plan Plan, report ValidationReport, switchLatencyMs float64) map[string]any {
	metrics := BuildAcceptanceMetrics(switchLatencyMs, report)
	return map[string]any{
		"plan":       plan,
		"validation": report,
		"metrics":    metrics,
	}
}

func BuildReportJSON(plan Plan, report ValidationReport, switchLatencyMs float64) ([]byte, error) {
	return json.MarshalIndent(BuildReport(plan, report, switchLatencyMs), "", "  ")
}

type contactInfo struct {
	Phone string
	Email string
}

func buildPrimaryContacts(personas []CurrentPersona) map[string]contactInfo {
	contacts := make(map[string]contactInfo)
	for _, persona := range personas {
		if !persona.IsPrimary {
			continue
		}
		contacts[strings.TrimSpace(persona.UserID)] = contactInfo{
			Phone: strings.TrimSpace(persona.Phone),
			Email: strings.TrimSpace(persona.Email),
		}
	}
	return contacts
}

func requestedHandle(persona CurrentPersona) string {
	for _, candidate := range []string{persona.Username, persona.Nickname, persona.PersonaID} {
		if normalized := normalizeHandle(candidate); normalized != "" {
			return normalized
		}
	}
	return ""
}

func normalizeHandle(input string) string {
	normalized := strings.ToLower(strings.TrimSpace(input))
	normalized = strings.ReplaceAll(normalized, "@", "")
	normalized = nonHandleChars.ReplaceAllString(normalized, ".")
	normalized = strings.Trim(normalized, ".")
	for strings.Contains(normalized, "..") {
		normalized = strings.ReplaceAll(normalized, "..", ".")
	}
	return normalized
}

func dedupeHandle(requested string, personaID string, reserved map[string]struct{}) string {
	base := requested
	if base == "" {
		base = normalizeHandle(personaID)
	}
	suffix := normalizeHandle(personaID)
	if suffix == "" {
		suffix = "persona"
	}
	candidate := base + "." + suffix
	if _, exists := reserved[candidate]; !exists {
		return candidate
	}
	for i := 2; ; i++ {
		candidate = base + "." + suffix + "." + anyString(i)
		if _, exists := reserved[candidate]; !exists {
			return candidate
		}
	}
}

func countBlank(values []string) int {
	count := 0
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			count++
		}
	}
	return count
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, strings.TrimSpace(value))
	}
	return out
}

func dedupeStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(values))
	out := make([]string, 0, len(values))
	for _, value := range values {
		normalized := strings.TrimSpace(value)
		if normalized == "" {
			continue
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	sort.Strings(out)
	return out
}

func countFindings(findings []ValidationFinding, code string) int {
	count := 0
	for _, finding := range findings {
		if finding.Code == code {
			count++
		}
	}
	return count
}

func anyString(value any) string {
	switch v := value.(type) {
	case nil:
		return ""
	case string:
		return v
	default:
		body, err := json.Marshal(v)
		if err != nil {
			return ""
		}
		return strings.Trim(strings.TrimSpace(string(body)), `"`)
	}
}
