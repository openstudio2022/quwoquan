package impact

import (
	"strconv"
	"strings"
)

// Target is a routable business-object reference shared by intersection and
// impact projections. ObjectType is the API object family; ObjectKind is the
// metadata object-kind discriminator inside that family.
type Target struct {
	ObjectType string `json:"objectType"`
	ObjectID   string `json:"objectId"`
	ObjectKind string `json:"objectKind"`
	RouteID    string `json:"routeId"`
}

// RepresentativeActor is the named, relationship-qualified actor from the
// same evidence snapshot as Count. A synthetic/anonymous actor is invalid.
type RepresentativeActor struct {
	ActorID         string  `json:"actorId"`
	DisplayName     string  `json:"displayName"`
	AvatarURL       string  `json:"avatarUrl"`
	RelationLabel   string  `json:"relationLabel"`
	PrivacyState    string  `json:"privacyState"`
	Target          *Target `json:"target"`
	EvidenceRank    int     `json:"evidenceRank"`
	SnapshotVersion string  `json:"snapshotVersion"`
}

type TextSpan struct {
	Text   string  `json:"text"`
	Role   string  `json:"role"`
	Target *Target `json:"target,omitempty"`
}

type Visual struct {
	AssetKind   string  `json:"assetKind"`
	ImageURL    string  `json:"imageUrl"`
	DisplayName string  `json:"displayName"`
	Target      *Target `json:"target,omitempty"`
}

type ActionHint struct {
	ActionKey          string   `json:"actionKey"`
	Label              string   `json:"label"`
	Target             *Target  `json:"target,omitempty"`
	IsPrimary          bool     `json:"isPrimary"`
	Priority           int      `json:"priority"`
	ActionTier         string   `json:"actionTier"`
	RequiredGates      []string `json:"requiredGates"`
	TargetAvailability string   `json:"targetAvailability"`
	Dispatch           string   `json:"dispatch"`
}

// Statement is the cloud-owned impact sentence contract. It intentionally has
// no compatibility displayText field: clients render PrimaryText and Spans.
type Statement struct {
	HelpType              string               `json:"helpType"`
	Action                string               `json:"action"`
	IntersectionDimension string               `json:"intersectionDimension"`
	TagRef                string               `json:"tagRef"`
	Source                string               `json:"source"`
	Count                 int64                `json:"count"`
	PrimaryText           string               `json:"primaryText"`
	SubtitleText          string               `json:"subtitleText"`
	ImpactID              string               `json:"impactId"`
	PrimarySpans          []TextSpan           `json:"primarySpans"`
	SampleVisuals         []Visual             `json:"sampleVisuals"`
	RepresentativeActor   *RepresentativeActor `json:"representativeActor"`
	ActionHints           []ActionHint         `json:"actionHints"`
	CountTarget           *Target              `json:"countTarget"`
	EvidenceSnapshotID    string               `json:"evidenceSnapshotId"`
	CountObjectKind       string               `json:"countObjectKind"`
	IconKey               string               `json:"iconKey"`
}

// StatementEvidence is the complete, persisted evidence needed to publish an
// impact statement. BuildStatement fails closed when any identity or routing
// anchor is absent; callers must never repair it with a fallback actor/text.
type StatementEvidence struct {
	HelpType              string
	Action                string
	IntersectionDimension string
	TagRef                string
	Source                string
	Count                 int64
	SubtitleText          string
	ImpactID              string
	EvidenceSnapshotID    string
	RepresentativeActor   RepresentativeActor
	ObjectName            string
	ObjectTarget          Target
	ObjectVisualURL       string
}

// BuildStatement creates a complete SVO statement and its structural spans.
// The bool is false for insufficient evidence; no partial statement is safe to
// expose to the App.
func BuildStatement(e StatementEvidence) (Statement, bool) {
	e = normalizeStatementEvidence(e)
	if !validStatementEvidence(e) {
		return Statement{}, false
	}
	prefix, suffix, ok := statementAffixes(e.HelpType, e.Action, e.Count)
	if !ok {
		return Statement{}, false
	}
	actorTarget := e.RepresentativeActor.Target
	objectTarget := e.ObjectTarget
	spans := []TextSpan{
		{Text: e.RepresentativeActor.DisplayName, Role: "actor", Target: actorTarget},
		{Text: prefix, Role: "plain"},
		{Text: e.ObjectName, Role: "object", Target: &objectTarget},
	}
	if suffix != "" {
		spans = append(spans, TextSpan{Text: suffix, Role: "plain"})
	}
	primaryText := joinTextSpans(spans)
	action := DefaultSummaryAction
	if configured, exists := SummaryActionByHelpType[e.HelpType]; exists {
		action = configured
	}
	iconKey := DefaultIconKey
	if configured := strings.TrimSpace(IconKeyByHelpType[e.HelpType]); configured != "" {
		iconKey = configured
	}
	actor := e.RepresentativeActor
	statement := Statement{
		HelpType:              e.HelpType,
		Action:                e.Action,
		IntersectionDimension: e.IntersectionDimension,
		TagRef:                e.TagRef,
		Source:                e.Source,
		Count:                 e.Count,
		PrimaryText:           primaryText,
		SubtitleText:          e.SubtitleText,
		ImpactID:              e.ImpactID,
		PrimarySpans:          spans,
		SampleVisuals:         []Visual{},
		RepresentativeActor:   &actor,
		ActionHints: []ActionHint{{
			ActionKey:          action.Key,
			Label:              action.Label,
			Target:             &objectTarget,
			IsPrimary:          true,
			Priority:           1,
			ActionTier:         "light",
			RequiredGates:      []string{},
			TargetAvailability: "available",
			Dispatch:           "navigate",
		}},
		CountTarget:        &objectTarget,
		EvidenceSnapshotID: e.EvidenceSnapshotID,
		CountObjectKind:    "person",
		IconKey:            iconKey,
	}
	if e.ObjectVisualURL != "" {
		statement.SampleVisuals = []Visual{{
			AssetKind:   "image",
			ImageURL:    e.ObjectVisualURL,
			DisplayName: e.ObjectName,
			Target:      &objectTarget,
		}}
	}
	return statement, true
}

func normalizeStatementEvidence(e StatementEvidence) StatementEvidence {
	e.HelpType = strings.TrimSpace(e.HelpType)
	e.Action = strings.TrimSpace(e.Action)
	e.IntersectionDimension = strings.TrimSpace(e.IntersectionDimension)
	e.TagRef = strings.TrimSpace(e.TagRef)
	e.Source = strings.TrimSpace(e.Source)
	e.SubtitleText = strings.TrimSpace(e.SubtitleText)
	e.ImpactID = strings.TrimSpace(e.ImpactID)
	e.EvidenceSnapshotID = strings.TrimSpace(e.EvidenceSnapshotID)
	e.ObjectName = strings.TrimSpace(e.ObjectName)
	e.ObjectVisualURL = strings.TrimSpace(e.ObjectVisualURL)
	e.ObjectTarget.ObjectType = strings.TrimSpace(e.ObjectTarget.ObjectType)
	e.ObjectTarget.ObjectID = strings.TrimSpace(e.ObjectTarget.ObjectID)
	e.ObjectTarget.ObjectKind = strings.TrimSpace(e.ObjectTarget.ObjectKind)
	e.ObjectTarget.RouteID = strings.TrimSpace(e.ObjectTarget.RouteID)
	e.RepresentativeActor.ActorID = strings.TrimSpace(e.RepresentativeActor.ActorID)
	e.RepresentativeActor.DisplayName = strings.TrimSpace(e.RepresentativeActor.DisplayName)
	e.RepresentativeActor.AvatarURL = strings.TrimSpace(e.RepresentativeActor.AvatarURL)
	e.RepresentativeActor.RelationLabel = strings.TrimSpace(e.RepresentativeActor.RelationLabel)
	e.RepresentativeActor.PrivacyState = strings.TrimSpace(e.RepresentativeActor.PrivacyState)
	e.RepresentativeActor.SnapshotVersion = strings.TrimSpace(e.RepresentativeActor.SnapshotVersion)
	if e.RepresentativeActor.PrivacyState == "" {
		e.RepresentativeActor.PrivacyState = "visible"
	}
	return e
}

func validStatementEvidence(e StatementEvidence) bool {
	if e.Count <= 0 || e.ImpactID == "" || e.EvidenceSnapshotID == "" || e.Source == "" || e.ObjectName == "" {
		return false
	}
	if e.ObjectTarget.ObjectType == "" || e.ObjectTarget.ObjectID == "" || e.ObjectTarget.RouteID == "" {
		return false
	}
	actor := e.RepresentativeActor
	if actor.ActorID == "" || actor.DisplayName == "" || actor.RelationLabel == "" || actor.Target == nil {
		return false
	}
	if actor.DisplayName == "用户" || actor.DisplayName == "有人" || strings.HasPrefix(actor.DisplayName, "一位") {
		return false
	}
	return actor.Target.ObjectType == "user" && actor.Target.ObjectID != "" && actor.Target.RouteID != ""
}

func statementAffixes(helpType, action string, count int64) (string, string, bool) {
	countSuffix := ""
	if count > 1 {
		countSuffix = "等" + strconv.FormatInt(count, 10) + "人"
	}
	switch helpType {
	case HelpRelationship:
		if action != "establish_connection" {
			return "", "", false
		}
		return countSuffix + "在", "建立了新连接", true
	case HelpCommunity:
		switch action {
		case "join_circle", "join":
			return countSuffix + "加入了", "", true
		case "start_discussion":
			return countSuffix + "围绕", "发起了讨论", true
		}
	case HelpDecision:
		return countSuffix + "通过相关记录关注了", "", true
	case HelpKnowledge:
		return countSuffix + "通过相关内容了解了", "", true
	case HelpSpread:
		if action == "active_participation" {
			return countSuffix + "最近参与了", "", true
		}
		return countSuffix + "分享了", "的相关记录", true
	case HelpAudience:
		return countSuffix + "看过", "的相关记录", true
	}
	return "", "", false
}

func joinTextSpans(spans []TextSpan) string {
	var b strings.Builder
	for _, span := range spans {
		b.WriteString(span.Text)
	}
	return b.String()
}
