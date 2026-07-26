package assistant

import "time"

const (
	SkillSubscriptionStatusActive   = "active"
	SkillSubscriptionStatusPaused   = "paused"
	SkillSubscriptionStatusArchived = "archived"
)

type SkillSubscriptionOwner struct {
	OwnerType string `bson:"ownerType" json:"ownerType"`
	OwnerID   string `bson:"ownerId" json:"ownerId"`
}

type SkillSubscriptionSearchQueryPlan struct {
	RawText string   `bson:"rawText" json:"rawText"`
	Queries []string `bson:"queries" json:"queries"`
}

type SkillSubscriptionTrigger struct {
	Type string `bson:"type" json:"type"`
	Cron string `bson:"cron" json:"cron"`
}

type SkillSubscriptionDestination struct {
	DestinationType  string `bson:"destinationType" json:"destinationType"`
	DestinationID    string `bson:"destinationId" json:"destinationId"`
	MaxPerDay        int    `bson:"maxPerDay,omitempty" json:"maxPerDay,omitempty"`
	CooldownMinutes  int    `bson:"cooldownMinutes,omitempty" json:"cooldownMinutes,omitempty"`
	QuietHoursPolicy string `bson:"quietHoursPolicy,omitempty" json:"quietHoursPolicy,omitempty"`
}

type SkillSubscriptionDeliveryState struct {
	PendingDeliveryID   string     `bson:"pendingDeliveryId,omitempty" json:"pendingDeliveryId,omitempty"`
	LastAttemptAt       *time.Time `bson:"lastAttemptAt,omitempty" json:"lastAttemptAt,omitempty"`
	LastDeliveredAt     *time.Time `bson:"lastDeliveredAt,omitempty" json:"lastDeliveredAt,omitempty"`
	NextAttemptAt       *time.Time `bson:"nextAttemptAt,omitempty" json:"nextAttemptAt,omitempty"`
	ConsecutiveFailures int        `bson:"consecutiveFailures" json:"consecutiveFailures"`
	LastErrorCode       string     `bson:"lastErrorCode,omitempty" json:"lastErrorCode,omitempty"`
}

type SkillSubscription struct {
	SubscriptionID     string                           `bson:"_id" json:"subscriptionId"`
	Owner              SkillSubscriptionOwner           `bson:"owner" json:"owner"`
	CreatedByUserID    string                           `bson:"createdByUserId" json:"createdByUserId"`
	CreatedByPersonaID string                           `bson:"createdByPersonaId,omitempty" json:"createdByPersonaId,omitempty"`
	SkillID            string                           `bson:"skillId" json:"skillId"`
	DomainID           string                           `bson:"domainId" json:"domainId"`
	TagRefs            []string                         `bson:"tagRefs" json:"tagRefs"`
	Status             string                           `bson:"status" json:"status"`
	SearchQueryPlan    SkillSubscriptionSearchQueryPlan `bson:"searchQueryPlan" json:"searchQueryPlan"`
	Trigger            SkillSubscriptionTrigger         `bson:"trigger" json:"trigger"`
	Destination        SkillSubscriptionDestination     `bson:"destination" json:"destination"`
	DeliveryState      SkillSubscriptionDeliveryState   `bson:"deliveryState" json:"deliveryState"`
	ClientRequestID    string                           `bson:"clientRequestId,omitempty" json:"clientRequestId,omitempty"`
	CreatedAt          time.Time                        `bson:"createdAt" json:"createdAt"`
	UpdatedAt          time.Time                        `bson:"updatedAt" json:"updatedAt"`
}

type CreateSkillSubscriptionInput struct {
	SkillID            string                           `json:"skillId"`
	DomainID           string                           `json:"domainId"`
	TagRefs            []string                         `json:"tagRefs"`
	SearchQueryPlan    SkillSubscriptionSearchQueryPlan `json:"searchQueryPlan"`
	Trigger            SkillSubscriptionTrigger         `json:"trigger"`
	Destination        SkillSubscriptionDestination     `json:"destination"`
	ClientRequestID    string                           `json:"clientRequestId"`
	CreatedByPersonaID string                           `json:"-"`
}

type UpsertSkillSubscriptionInput struct {
	SubscriptionID     string
	SkillID            string
	DomainID           string
	TagRefs            []string
	Status             string
	SearchQueryPlan    SkillSubscriptionSearchQueryPlan
	Trigger            SkillSubscriptionTrigger
	Destination        SkillSubscriptionDestination
	CreatedByPersonaID string
}

type UpdateSkillSubscriptionStatusInput struct {
	Status string `json:"status"`
}

type SkillSubscriptionListView struct {
	Items []SkillSubscription `json:"items"`
}

type SkillSubscriptionCronTickInput struct {
	Now string `json:"now"`
}

type SkillSubscriptionCronTickResult struct {
	ProcessedCount    int      `json:"processedCount"`
	SuppressedCount   int      `json:"suppressedCount"`
	FailedCount       int      `json:"failedCount"`
	CreatedTurnIDs    []string `json:"createdTurnIds"`
	CreatedMessageIDs []string `json:"createdMessageIds"`
}
