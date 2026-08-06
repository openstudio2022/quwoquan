package gatheringplan

import "time"

type PlanItemKind string

const (
	PlanItemKindAgenda       PlanItemKind = "agenda"
	PlanItemKindPlace        PlanItemKind = "place"
	PlanItemKindRouteSegment PlanItemKind = "route_segment"
	PlanItemKindTask         PlanItemKind = "task"
	PlanItemKindChecklist    PlanItemKind = "checklist"
	PlanItemKindNote         PlanItemKind = "note"
)

type PlanTravelMode string

const (
	PlanTravelModeWalk    PlanTravelMode = "walk"
	PlanTravelModeBicycle PlanTravelMode = "bicycle"
	PlanTravelModeTransit PlanTravelMode = "transit"
	PlanTravelModeDrive   PlanTravelMode = "drive"
	PlanTravelModeFerry   PlanTravelMode = "ferry"
	PlanTravelModeOther   PlanTravelMode = "other"
)

type PlanAcknowledgementMode string

const (
	PlanAcknowledgementModeNone                   PlanAcknowledgementMode = "none"
	PlanAcknowledgementModeAffectedParticipations PlanAcknowledgementMode = "affected_participations"
)

type PlanAcknowledgementStatus string

const (
	PlanAcknowledgementStatusPending      PlanAcknowledgementStatus = "pending"
	PlanAcknowledgementStatusAcknowledged PlanAcknowledgementStatus = "acknowledged"
	PlanAcknowledgementStatusDeclined     PlanAcknowledgementStatus = "declined"
)

type ProposalStatus string

const (
	ProposalStatusPending   ProposalStatus = "pending"
	ProposalStatusCommitted ProposalStatus = "committed"
)

type SourceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type ParticipationRef struct {
	GatheringID string `json:"gatheringId" bson:"gatheringId"`
	PersonaID   string `json:"personaId" bson:"personaId"`
}

type AgendaItem struct {
	Content         string     `json:"content" bson:"content"`
	StartsAt        *time.Time `json:"startsAt,omitempty" bson:"startsAt,omitempty"`
	DurationMinutes *int       `json:"durationMinutes,omitempty" bson:"durationMinutes,omitempty"`
}

type PlaceItem struct {
	PlaceRef    SourceRef `json:"placeRef" bson:"placeRef"`
	Instruction string    `json:"instruction,omitempty" bson:"instruction,omitempty"`
}

type RouteSegmentItem struct {
	FromPlaceRef     SourceRef      `json:"fromPlaceRef" bson:"fromPlaceRef"`
	ToPlaceRef       SourceRef      `json:"toPlaceRef" bson:"toPlaceRef"`
	TravelMode       PlanTravelMode `json:"travelMode" bson:"travelMode"`
	EstimatedMinutes *int           `json:"estimatedMinutes,omitempty" bson:"estimatedMinutes,omitempty"`
	Instruction      string         `json:"instruction,omitempty" bson:"instruction,omitempty"`
}

type TaskItem struct {
	Content   string     `json:"content" bson:"content"`
	DueAt     *time.Time `json:"dueAt,omitempty" bson:"dueAt,omitempty"`
	Completed bool       `json:"completed" bson:"completed"`
}

type ChecklistEntry struct {
	EntryID string `json:"entryId" bson:"entryId"`
	Content string `json:"content" bson:"content"`
	Checked bool   `json:"checked" bson:"checked"`
}

type ChecklistItem struct {
	Entries []ChecklistEntry `json:"entries" bson:"entries"`
}

type NoteItem struct {
	Content string `json:"content" bson:"content"`
}

// PlanItem is a closed typed union. Exactly one payload matching Kind must be
// present; Map/dynamic extension fields are intentionally impossible.
type PlanItem struct {
	ItemID       string            `json:"itemId" bson:"itemId"`
	Kind         PlanItemKind      `json:"kind" bson:"kind"`
	Order        int               `json:"order" bson:"order"`
	Agenda       *AgendaItem       `json:"agenda,omitempty" bson:"agenda,omitempty"`
	Place        *PlaceItem        `json:"place,omitempty" bson:"place,omitempty"`
	RouteSegment *RouteSegmentItem `json:"routeSegment,omitempty" bson:"routeSegment,omitempty"`
	Task         *TaskItem         `json:"task,omitempty" bson:"task,omitempty"`
	Checklist    *ChecklistItem    `json:"checklist,omitempty" bson:"checklist,omitempty"`
	Note         *NoteItem         `json:"note,omitempty" bson:"note,omitempty"`
	AssigneeRef  *ParticipationRef `json:"assigneeRef,omitempty" bson:"assigneeRef,omitempty"`
	SourceRefs   []SourceRef       `json:"sourceRefs" bson:"sourceRefs"`
}

type AcknowledgementPolicy struct {
	Mode       PlanAcknowledgementMode `json:"mode" bson:"mode"`
	DeadlineAt *time.Time              `json:"deadlineAt,omitempty" bson:"deadlineAt,omitempty"`
}

type RevisionAcknowledgement struct {
	RevisionID       string                    `json:"revisionId" bson:"revisionId"`
	ParticipationRef ParticipationRef          `json:"participationRef" bson:"participationRef"`
	Status           PlanAcknowledgementStatus `json:"status" bson:"status"`
	EvidenceRef      *SourceRef                `json:"evidenceRef,omitempty" bson:"evidenceRef,omitempty"`
	RecordedAt       *time.Time                `json:"recordedAt,omitempty" bson:"recordedAt,omitempty"`
}

type Revision struct {
	RevisionID                string                `json:"revisionId" bson:"revisionId"`
	RevisionNumber            int                   `json:"revisionNumber" bson:"revisionNumber"`
	BaseRevisionID            string                `json:"baseRevisionId,omitempty" bson:"baseRevisionId,omitempty"`
	BaseRevisionNumber        int                   `json:"baseRevisionNumber" bson:"baseRevisionNumber"`
	BaseRevisionDigest        string                `json:"baseRevisionDigest" bson:"baseRevisionDigest"`
	RevisionDigest            string                `json:"revisionDigest" bson:"revisionDigest"`
	CommittedProposalID       string                `json:"committedProposalId,omitempty" bson:"committedProposalId,omitempty"`
	CommittedByPersonaID      string                `json:"committedByPersonaId" bson:"committedByPersonaId"`
	Items                     []PlanItem            `json:"items" bson:"items"`
	AcknowledgementPolicy     AcknowledgementPolicy `json:"acknowledgementPolicy" bson:"acknowledgementPolicy"`
	AffectedParticipationRefs []ParticipationRef    `json:"affectedParticipationRefs" bson:"affectedParticipationRefs"`
	CommittedAt               time.Time             `json:"committedAt" bson:"committedAt"`
}

type Proposal struct {
	ProposalID                string                `json:"proposalId" bson:"proposalId"`
	BasePlanVersion           int64                 `json:"basePlanVersion" bson:"basePlanVersion"`
	BaseRevisionID            string                `json:"baseRevisionId" bson:"baseRevisionId"`
	BaseRevisionNumber        int                   `json:"baseRevisionNumber" bson:"baseRevisionNumber"`
	BaseRevisionDigest        string                `json:"baseRevisionDigest" bson:"baseRevisionDigest"`
	ProposalDigest            string                `json:"proposalDigest" bson:"proposalDigest"`
	ProposedByPersonaID       string                `json:"proposedByPersonaId" bson:"proposedByPersonaId"`
	Items                     []PlanItem            `json:"items" bson:"items"`
	AcknowledgementPolicy     AcknowledgementPolicy `json:"acknowledgementPolicy" bson:"acknowledgementPolicy"`
	AffectedParticipationRefs []ParticipationRef    `json:"affectedParticipationRefs" bson:"affectedParticipationRefs"`
	Status                    ProposalStatus        `json:"status" bson:"status"`
	ProposedAt                time.Time             `json:"proposedAt" bson:"proposedAt"`
	CommittedRevisionID       string                `json:"committedRevisionId,omitempty" bson:"committedRevisionId,omitempty"`
	CommittedAt               *time.Time            `json:"committedAt,omitempty" bson:"committedAt,omitempty"`
}

// GatheringPlan owns plan collaboration only. It deliberately contains no
// Gathering title, schedule, Host, Participation state, capacity, lifecycle,
// Outcome or conversation fields.
type GatheringPlan struct {
	ID                    string                    `json:"id" bson:"_id"`
	GatheringID           string                    `json:"gatheringId" bson:"gatheringId"`
	Version               int64                     `json:"version" bson:"version"`
	CurrentRevisionID     string                    `json:"currentRevisionId" bson:"currentRevisionId"`
	CurrentRevisionNumber int                       `json:"currentRevisionNumber" bson:"currentRevisionNumber"`
	CurrentRevisionDigest string                    `json:"currentRevisionDigest" bson:"currentRevisionDigest"`
	Revisions             []Revision                `json:"revisions" bson:"revisions"`
	Proposals             []Proposal                `json:"proposals" bson:"proposals"`
	Acknowledgements      []RevisionAcknowledgement `json:"acknowledgements" bson:"acknowledgements"`
	CreatedAt             time.Time                 `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time                 `json:"updatedAt" bson:"updatedAt"`
}

type CommandResult struct {
	PlanID                string `json:"planId" bson:"planId"`
	GatheringID           string `json:"gatheringId" bson:"gatheringId"`
	PlanVersion           int64  `json:"planVersion" bson:"planVersion"`
	CurrentRevisionID     string `json:"currentRevisionId" bson:"currentRevisionId"`
	CurrentRevisionNumber int    `json:"currentRevisionNumber" bson:"currentRevisionNumber"`
	CurrentRevisionDigest string `json:"currentRevisionDigest" bson:"currentRevisionDigest"`
	ProposalID            string `json:"proposalId,omitempty" bson:"proposalId,omitempty"`
	ProposalDigest        string `json:"proposalDigest,omitempty" bson:"proposalDigest,omitempty"`
	Replayed              bool   `json:"replayed" bson:"replayed"`
}

type RevisionPage struct {
	Items      []Revision `json:"items"`
	NextCursor string     `json:"nextCursor,omitempty"`
	HasMore    bool       `json:"hasMore"`
}

type EventPayload struct {
	PlanID           string    `json:"planId"`
	GatheringID      string    `json:"gatheringId"`
	AggregateVersion int64     `json:"aggregateVersion"`
	ActorPersonaID   string    `json:"actorPersonaId"`
	ProposalID       string    `json:"proposalId,omitempty"`
	ProposalDigest   string    `json:"proposalDigest,omitempty"`
	RevisionID       string    `json:"revisionId"`
	RevisionNumber   int       `json:"revisionNumber"`
	RevisionDigest   string    `json:"revisionDigest"`
	OccurredAt       time.Time `json:"occurredAt"`
}
