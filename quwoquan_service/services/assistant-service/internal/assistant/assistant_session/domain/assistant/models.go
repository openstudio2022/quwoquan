package assistant

import "time"

type AssistantEntryPersonalizationChipView struct {
	ChipID     string `json:"chipId"`
	Label      string `json:"label"`
	ActionType string `json:"actionType"`
	Value      string `json:"value,omitempty"`
}

type AssistantEntryPersonalizationView struct {
	WelcomeMessage      string                                  `json:"welcomeMessage"`
	SuggestionLines     []string                                `json:"suggestionLines"`
	Chips               []AssistantEntryPersonalizationChipView `json:"chips"`
	Personalized        bool                                    `json:"personalized"`
	MatchedInterestTags []string                                `json:"matchedInterestTags,omitempty"`
	MatchedSegments     []string                                `json:"matchedSegments,omitempty"`
	LifecycleStage      string                                  `json:"lifecycleStage,omitempty"`
}

type SuggestedAction struct {
	ActionID string         `json:"actionId"`
	Type     string         `json:"type"`
	Label    string         `json:"label"`
	Icon     string         `json:"icon,omitempty"`
	Payload  map[string]any `json:"payload,omitempty"`
}

type SuggestedActionListView struct {
	Items []SuggestedAction `json:"items"`
}

type PageContextAck struct {
	Accepted   bool       `json:"accepted"`
	ContextKey string     `json:"contextKey"`
	ExpiresAt  *time.Time `json:"expiresAt,omitempty"`
}

type AssistantUserTaskView struct {
	TaskID        string `json:"taskId"`
	Title         string `json:"title"`
	Description   string `json:"description,omitempty"`
	Status        string `json:"status"`
	DueAt         string `json:"dueAt,omitempty"`
	Priority      string `json:"priority,omitempty"`
	SourceSkillID string `json:"sourceSkillId,omitempty"`
	UpdatedAt     string `json:"updatedAt,omitempty"`
}

type AssistantUserTaskListView struct {
	Items []AssistantUserTaskView `json:"items"`
}

type AssistantSuggestedHomepageView struct {
	ID                string `json:"id"`
	Type              string `json:"type"`
	CanonicalEntityID string `json:"canonicalEntityId,omitempty"`
	DisplayName       string `json:"displayName"`
	Reason            string `json:"reason,omitempty"`
}

type AssistantCreationSuggestRequest struct {
	DraftTitle        string   `json:"draftTitle,omitempty"`
	DraftSummary      string   `json:"draftSummary,omitempty"`
	BodyDigest        string   `json:"bodyDigest,omitempty"`
	BoundCircleIDs    []string `json:"boundCircleIds,omitempty"`
	PrimaryHomepageID string   `json:"primaryHomepageId,omitempty"`
}

type AssistantCreationSuggestResponse struct {
	SuggestedTagRefs   []string                         `json:"suggestedTagRefs"`
	SuggestedHomepages []AssistantSuggestedHomepageView `json:"suggestedHomepages"`
	SuggestedTitle     string                           `json:"suggestedTitle,omitempty"`
	SuggestedSummary   string                           `json:"suggestedSummary,omitempty"`
	Available          bool                             `json:"available"`
	UnavailableReason  string                           `json:"unavailableReason,omitempty"`
}

// CitationDestination 是引用跳转的唯一 wire 形态：站内引用只传 canonical
// object type/id，站外引用只传已验证 HTTPS URL。
type CitationDestination struct {
	Kind          string `json:"kind"`
	ObjectTypeRef string `json:"objectTypeRef,omitempty"`
	ObjectID      string `json:"objectId,omitempty"`
	URL           string `json:"url,omitempty"`
}

type AssistantSearchCitationView struct {
	CitationID    string              `json:"citationId"`
	ObjectType    string              `json:"objectType"`
	ObjectID      string              `json:"objectId"`
	Title         string              `json:"title"`
	ContentType   string              `json:"contentType,omitempty"`
	Snippet       string              `json:"snippet,omitempty"`
	CoverURL      string              `json:"coverUrl,omitempty"`
	BadgeLabel    string              `json:"badgeLabel,omitempty"`
	SourceDomain  string              `json:"sourceDomain,omitempty"`
	Destination   CitationDestination `json:"destination"`
	Score         float64             `json:"score,omitempty"`
	RecallSource  string              `json:"recallSource,omitempty"`
	ObjectTypeRef string              `json:"objectTypeRef,omitempty"`
}

type AssistantSearchResultView struct {
	QueryEcho       string                        `json:"queryEcho"`
	Summary         string                        `json:"summary,omitempty"`
	SearchIntensity string                        `json:"searchIntensity,omitempty"`
	Citations       []AssistantSearchCitationView `json:"citations"`
}

type PageContextInput struct {
	ContextSnapshot AssistantContextSnapshot `json:"contextSnapshot"`
}

type SearchRequest struct {
	UserQuery             string                    `json:"userQuery"`
	SearchIntensity       string                    `json:"searchIntensity,omitempty"`
	PersonaID             string                    `json:"personaId,omitempty"`
	PersonaContextVersion string                    `json:"personaContextVersion,omitempty"`
	SourceSurfaceID       string                    `json:"sourceSurfaceId,omitempty"`
	FromGlobalSearch      bool                      `json:"fromGlobalSearch,omitempty"`
	ContextSnapshot       *AssistantContextSnapshot `json:"contextSnapshot,omitempty"`
}
