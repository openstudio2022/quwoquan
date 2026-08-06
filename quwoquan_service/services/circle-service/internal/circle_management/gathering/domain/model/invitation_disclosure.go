package gathering

import (
	"strings"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

// DisclosureScheduleSnapshot and DisclosurePlaceSnapshot are pure domain
// projections shared by public queries and invitation outbox payloads. Keeping
// the policy decision here prevents the event path from inventing a second
// disclosure interpretation.
type DisclosureScheduleSnapshot struct {
	Timezone  string
	StartAt   time.Time
	EndAt     time.Time
	DateLabel string
}

type DisclosurePlaceSnapshot struct {
	Mode              contract.GatheringPlaceMode
	CoarsePlaceLabel  string
	ExactMeetingPoint string
	CoarseVisible     bool
	ExactVisible      bool
}

func ProjectDisclosureSchedule(
	value contract.GatheringSchedule,
	disclosure contract.GatheringDisclosurePolicy,
	hasJoinedAccess bool,
) DisclosureScheduleSnapshot {
	result := DisclosureScheduleSnapshot{Timezone: normalizedTimezone(value.Timezone)}
	canSeeExact := disclosure.TimeDisclosure == contract.GatheringTimeDisclosureExact ||
		(disclosure.TimeDisclosure == contract.GatheringTimeDisclosureAfterJoin &&
			hasJoinedAccess)
	if canSeeExact {
		result.StartAt = utcOrZeroDisclosure(value.StartAt)
		result.EndAt = utcOrZeroDisclosure(value.EndAt)
		return result
	}
	if disclosure.TimeDisclosure == contract.GatheringTimeDisclosureDateOnly {
		result.DateLabel = disclosureDateLabel(value)
	}
	return result
}

func ProjectDisclosurePlace(
	value contract.GatheringPlace,
	disclosure contract.GatheringDisclosurePolicy,
	hasJoinedAccess bool,
) DisclosurePlaceSnapshot {
	result := DisclosurePlaceSnapshot{Mode: value.Mode}
	canSeeExact := disclosure.PlaceDisclosure == contract.GatheringPlaceDisclosureExact ||
		(disclosure.PlaceDisclosure == contract.GatheringPlaceDisclosureAfterJoin &&
			hasJoinedAccess)
	if disclosure.PlaceDisclosure == contract.GatheringPlaceDisclosureCoarse || canSeeExact {
		result.CoarseVisible = true
		result.CoarsePlaceLabel = strings.TrimSpace(value.CoarsePlaceLabel)
	}
	if canSeeExact {
		result.ExactVisible = true
		result.ExactMeetingPoint = strings.TrimSpace(value.ExactMeetingPoint)
	}
	return result
}

func normalizedTimezone(value string) string {
	if normalized := strings.TrimSpace(value); normalized != "" {
		return normalized
	}
	return "UTC"
}

func disclosureDateLabel(value contract.GatheringSchedule) string {
	if value.StartAt.IsZero() {
		return ""
	}
	location := time.UTC
	if timezone := strings.TrimSpace(value.Timezone); timezone != "" {
		if loaded, err := time.LoadLocation(timezone); err == nil {
			location = loaded
		}
	}
	start := value.StartAt.In(location).Format(time.DateOnly)
	if value.EndAt.IsZero() {
		return start
	}
	end := value.EndAt.In(location).Format(time.DateOnly)
	if end == start {
		return start
	}
	return start + "/" + end
}

func utcOrZeroDisclosure(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC()
}
