package assistant

import "time"

type InteractionEvent struct {
	EventID                 string    `bson:"_id" json:"eventId"`
	RunID                   string    `bson:"runId" json:"runId"`
	TraceID                 string    `bson:"traceId,omitempty" json:"traceId,omitempty"`
	UserID                  string    `bson:"userId" json:"userId"`
	SessionID               string    `bson:"sessionId" json:"sessionId"`
	PageType                string    `bson:"pageType" json:"pageType"`
	DomainID                string    `bson:"domainId" json:"domainId"`
	PageID                  string    `bson:"pageId,omitempty" json:"pageId,omitempty"`
	SurfaceID               string    `bson:"surfaceId,omitempty" json:"surfaceId,omitempty"`
	RouteID                 string    `bson:"routeId,omitempty" json:"routeId,omitempty"`
	OperationID             string    `bson:"operationId,omitempty" json:"operationId,omitempty"`
	ExperimentBucket        string    `bson:"experimentBucket,omitempty" json:"experimentBucket,omitempty"`
	ClientSentAt            string    `bson:"clientSentAt,omitempty" json:"clientSentAt,omitempty"`
	QueryText               string    `bson:"queryText,omitempty" json:"queryText,omitempty"`
	AnswerText              string    `bson:"answerText,omitempty" json:"answerText,omitempty"`
	UserTags                []string  `bson:"userTags,omitempty" json:"userTags,omitempty"`
	DurationMs              int       `bson:"durationMs,omitempty" json:"durationMs,omitempty"`
	ExplicitThumb           string    `bson:"explicitThumb,omitempty" json:"explicitThumb,omitempty"`
	ExplicitReasonCodes     []string  `bson:"explicitReasonCodes,omitempty" json:"explicitReasonCodes,omitempty"`
	CopiedAnswer            bool      `bson:"copiedAnswer" json:"copiedAnswer"`
	SharedAnswer            bool      `bson:"sharedAnswer" json:"sharedAnswer"`
	FavoritedAnswer         bool      `bson:"favoritedAnswer" json:"favoritedAnswer"`
	RegeneratedAnswer       bool      `bson:"regeneratedAnswer" json:"regeneratedAnswer"`
	StyleAdjusted           bool      `bson:"styleAdjusted" json:"styleAdjusted"`
	ModelSwitched           bool      `bson:"modelSwitched" json:"modelSwitched"`
	ReferenceOpened         bool      `bson:"referenceOpened" json:"referenceOpened"`
	Interrupted             bool      `bson:"interrupted" json:"interrupted"`
	FeedbackTargetMessageID string    `bson:"feedbackTargetMessageId,omitempty" json:"feedbackTargetMessageId,omitempty"`
	CorrectionText          string    `bson:"correctionText,omitempty" json:"correctionText,omitempty"`
	EventType               string    `bson:"eventType,omitempty" json:"eventType,omitempty"`
	FeedbackType            string    `bson:"feedbackType,omitempty" json:"feedbackType,omitempty"`
	FeedbackScore           float64   `bson:"feedbackScore,omitempty" json:"feedbackScore,omitempty"`
	FeedbackText            string    `bson:"feedbackText,omitempty" json:"feedbackText,omitempty"`
	CreatedAt               time.Time `bson:"createdAt" json:"createdAt"`
}

type Scorecard struct {
	ScoreID          string    `bson:"_id" json:"scoreId"`
	EventID          string    `bson:"eventId" json:"eventId"`
	RunID            string    `bson:"runId,omitempty" json:"runId,omitempty"`
	UserID           string    `bson:"userId" json:"userId"`
	DomainID         string    `bson:"domainId" json:"domainId"`
	PageID           string    `bson:"pageId,omitempty" json:"pageId,omitempty"`
	SurfaceID        string    `bson:"surfaceId,omitempty" json:"surfaceId,omitempty"`
	RouteID          string    `bson:"routeId,omitempty" json:"routeId,omitempty"`
	OperationID      string    `bson:"operationId,omitempty" json:"operationId,omitempty"`
	ExperimentBucket string    `bson:"experimentBucket,omitempty" json:"experimentBucket,omitempty"`
	MetricID         string    `bson:"metricId" json:"metricId"`
	ScoreValue       float64   `bson:"scoreValue" json:"scoreValue"`
	ScoreSource      string    `bson:"scoreSource" json:"scoreSource"`
	CreatedAt        time.Time `bson:"createdAt" json:"createdAt"`
}

type AssistantLearningProfile struct {
	UserID                 string             `bson:"userId" json:"userId"`
	LastRunID              string             `bson:"lastRunId,omitempty" json:"lastRunId,omitempty"`
	LastEventID            string             `bson:"lastEventId,omitempty" json:"lastEventId,omitempty"`
	LastPageType           string             `bson:"lastPageType,omitempty" json:"lastPageType,omitempty"`
	LastFeedbackType       string             `bson:"lastFeedbackType,omitempty" json:"lastFeedbackType,omitempty"`
	LastFeedbackText       string             `bson:"lastFeedbackText,omitempty" json:"lastFeedbackText,omitempty"`
	LastFeedbackScore      float64            `bson:"lastFeedbackScore,omitempty" json:"lastFeedbackScore,omitempty"`
	LastFeedbackAt         time.Time          `bson:"lastFeedbackAt,omitempty" json:"lastFeedbackAt,omitempty"`
	LastQueryTextDigest    string             `bson:"lastQueryTextDigest,omitempty" json:"lastQueryTextDigest,omitempty"`
	LastAnswerTextDigest   string             `bson:"lastAnswerTextDigest,omitempty" json:"lastAnswerTextDigest,omitempty"`
	LastMetricID           string             `bson:"lastMetricId,omitempty" json:"lastMetricId,omitempty"`
	LastMetricScore        float64            `bson:"lastMetricScore,omitempty" json:"lastMetricScore,omitempty"`
	TotalFeedbackCount     int64              `bson:"totalFeedbackCount,omitempty" json:"totalFeedbackCount,omitempty"`
	PositiveFeedbackCount  int64              `bson:"positiveFeedbackCount,omitempty" json:"positiveFeedbackCount,omitempty"`
	NegativeFeedbackCount  int64              `bson:"negativeFeedbackCount,omitempty" json:"negativeFeedbackCount,omitempty"`
	TextFeedbackCount      int64              `bson:"textFeedbackCount,omitempty" json:"textFeedbackCount,omitempty"`
	HighPriorityCount      int64              `bson:"highPriorityCount,omitempty" json:"highPriorityCount,omitempty"`
	MediumPriorityCount    int64              `bson:"mediumPriorityCount,omitempty" json:"mediumPriorityCount,omitempty"`
	MetricSampleCounts     map[string]int64   `bson:"metricSampleCounts,omitempty" json:"metricSampleCounts,omitempty"`
	MetricScoreSums        map[string]float64 `bson:"metricScoreSums,omitempty" json:"metricScoreSums,omitempty"`
	LatestMetricScores     map[string]float64 `bson:"latestMetricScores,omitempty" json:"latestMetricScores,omitempty"`
	ReasonCodeCounts       map[string]int64   `bson:"reasonCodeCounts,omitempty" json:"reasonCodeCounts,omitempty"`
	UpdatedAt              time.Time          `bson:"updatedAt,omitempty" json:"updatedAt,omitempty"`
}

type SkillConsent struct {
	ID           string     `json:"id"`
	UserID       string     `json:"userId"`
	SkillID      string     `json:"skillId"`
	GrantedScope string     `json:"grantedScope"`
	GrantedAt    time.Time  `json:"grantedAt"`
	RevokedAt    *time.Time `json:"revokedAt,omitempty"`
}

type AssistantPolicyView struct {
	Version   string         `json:"version"`
	Values    map[string]any `json:"values,omitempty"`
	UpdatedAt *time.Time     `json:"updatedAt,omitempty"`
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

type AssistantUserMemoryView struct {
	MemoryID   string `json:"memoryId"`
	Title      string `json:"title"`
	Snippet    string `json:"snippet,omitempty"`
	SourceType string `json:"sourceType,omitempty"`
	CreatedAt  string `json:"createdAt,omitempty"`
	UpdatedAt  string `json:"updatedAt,omitempty"`
}

type AssistantUserMemoryListView struct {
	Items []AssistantUserMemoryView `json:"items"`
}

type AssistantLearningOpsSummaryView struct {
	UserID                string             `json:"userId"`
	TotalFeedbackCount    int64              `json:"totalFeedbackCount"`
	PositiveFeedbackCount int64              `json:"positiveFeedbackCount"`
	NegativeFeedbackCount int64              `json:"negativeFeedbackCount"`
	TextFeedbackCount     int64              `json:"textFeedbackCount"`
	HighPriorityCount     int64              `json:"highPriorityCount"`
	MediumPriorityCount   int64              `json:"mediumPriorityCount"`
	LastFeedbackType      string             `json:"lastFeedbackType,omitempty"`
	LastFeedbackScore     float64            `json:"lastFeedbackScore,omitempty"`
	LastFeedbackAt        string             `json:"lastFeedbackAt,omitempty"`
	LastMetricID          string             `json:"lastMetricId,omitempty"`
	LastMetricScore       float64            `json:"lastMetricScore,omitempty"`
	TopReasonCodes        []string           `json:"topReasonCodes,omitempty"`
	MetricAverages        map[string]float64 `json:"metricAverages,omitempty"`
	LatestMetricScores    map[string]float64 `json:"latestMetricScores,omitempty"`
	UpdatedAt             string             `json:"updatedAt,omitempty"`
}

type AssistantSkillCatalogItemView struct {
	SkillID         string `json:"skillId"`
	DisplayName     string `json:"displayName"`
	Description     string `json:"description,omitempty"`
	Category        string `json:"category,omitempty"`
	RequiresConsent bool   `json:"requiresConsent"`
	IconHint        string `json:"iconHint,omitempty"`
}

type AssistantSkillCatalogListView struct {
	Items []AssistantSkillCatalogItemView `json:"items"`
}

type AssistantSearchCitationView struct {
	CitationID   string `json:"citationId"`
	ObjectType   string `json:"objectType"`
	ObjectID     string `json:"objectId"`
	Title        string `json:"title"`
	ContentType  string `json:"contentType,omitempty"`
	Snippet      string `json:"snippet,omitempty"`
	CoverURL     string `json:"coverUrl,omitempty"`
	BadgeLabel   string `json:"badgeLabel,omitempty"`
	SourceDomain string `json:"sourceDomain,omitempty"`
}

type AssistantSearchResultView struct {
	QueryEcho       string                        `json:"queryEcho"`
	Summary         string                        `json:"summary,omitempty"`
	SearchIntensity string                        `json:"searchIntensity,omitempty"`
	Citations       []AssistantSearchCitationView `json:"citations"`
}

type PageContextInput struct {
	PageType              string           `json:"pageType"`
	BusinessObjects       []map[string]any `json:"businessObjects,omitempty"`
	UserAction            string           `json:"userAction,omitempty"`
	UserActions           []string         `json:"userActions,omitempty"`
	ProfileSubjectID      string           `json:"profileSubjectId,omitempty"`
	SubAccountID          string           `json:"subAccountId,omitempty"`
	PersonaContextVersion string           `json:"personaContextVersion,omitempty"`
}

type SearchRequest struct {
	UserQuery             string `json:"userQuery"`
	SearchIntensity       string `json:"searchIntensity,omitempty"`
	ProfileSubjectID      string `json:"profileSubjectId,omitempty"`
	SubAccountID          string `json:"subAccountId,omitempty"`
	PersonaContextVersion string `json:"personaContextVersion,omitempty"`
	SourceSurfaceID       string `json:"sourceSurfaceId,omitempty"`
	FromGlobalSearch      bool   `json:"fromGlobalSearch,omitempty"`
}
