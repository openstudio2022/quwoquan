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
	DestinationType string `bson:"destinationType" json:"destinationType"`
	DestinationID   string `bson:"destinationId" json:"destinationId"`
}

type SkillSubscription struct {
	SubscriptionID  string                           `bson:"_id" json:"subscriptionId"`
	Owner           SkillSubscriptionOwner           `bson:"owner" json:"owner"`
	CreatedByUserID string                           `bson:"createdByUserId" json:"createdByUserId"`
	SkillID         string                           `bson:"skillId" json:"skillId"`
	DomainID        string                           `bson:"domainId" json:"domainId"`
	TagRefs         []string                         `bson:"tagRefs" json:"tagRefs"`
	Status          string                           `bson:"status" json:"status"`
	SearchQueryPlan SkillSubscriptionSearchQueryPlan `bson:"searchQueryPlan" json:"searchQueryPlan"`
	Trigger         SkillSubscriptionTrigger         `bson:"trigger" json:"trigger"`
	Destination     SkillSubscriptionDestination     `bson:"destination" json:"destination"`
	CreatedAt       time.Time                        `bson:"createdAt" json:"createdAt"`
	UpdatedAt       time.Time                        `bson:"updatedAt" json:"updatedAt"`
}

type CreateSkillSubscriptionInput struct {
	SkillID         string                           `json:"skillId"`
	DomainID        string                           `json:"domainId"`
	TagRefs         []string                         `json:"tagRefs"`
	SearchQueryPlan SkillSubscriptionSearchQueryPlan `json:"searchQueryPlan"`
	Trigger         SkillSubscriptionTrigger         `json:"trigger"`
	Destination     SkillSubscriptionDestination     `json:"destination"`
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
	CreatedTurnIDs    []string `json:"createdTurnIds"`
	CreatedMessageIDs []string `json:"createdMessageIds"`
}
