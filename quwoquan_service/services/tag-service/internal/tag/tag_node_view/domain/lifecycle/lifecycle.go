// Package lifecycle owns the meaning of TagLifecycleStatus.
//
// The enum grew from active|deprecated to active|trending|seasonal|campaign|
// deprecated. Four of the five values are usable; only deprecated is not.
// Availability must therefore be decided by IsUsable rather than by comparing
// against the literal "active": a direct comparison silently treats trending,
// seasonal and campaign tags as retired, which would make a campaign tag
// unresolvable for the whole duration of the campaign it was created for.
//
// Read paths that filter in storage must use UsableStatuses so the projected
// predicate and the in-memory predicate stay the same set. An unrecognized
// value is not usable: the projection is written by the version-locked tag
// importer from an immutable release, so an unknown status means corrupt data
// rather than a newer vocabulary.
package lifecycle

import (
	"fmt"
	"strings"
	"time"

	nodecontract "quwoquan_service/services/tag-service/generated/tag/tag_node_view/contract/tag"
)

// Window is the projected heat window shape, reused from the generated contract
// so the importer, the store and the read views cannot drift apart.
type Window = nodecontract.TagHeatWindow

// WindowDeclaration is the on-disk form of a heat window. Timestamps stay
// strings here because the taxonomy release is authored as JSON and a malformed
// timestamp must fail the import rather than decode to the zero time, which the
// recommendation side would read as "hot since year zero".
type WindowDeclaration struct {
	StartAt    string `json:"startAt"`
	EndAt      string `json:"endAt"`
	Recurrence string `json:"recurrence"`
}

const (
	// RecurrenceOnce is a window that happens exactly once, for campaigns.
	RecurrenceOnce = "once"
	// RecurrenceAnnual is a window that repeats every year, for seasons.
	RecurrenceAnnual = "annual"
)

// ResolveDeclaration validates a taxonomy definition's lifecycle declaration.
//
// An omitted status means active, which is what every definition authored before
// the enum existed intends. seasonal and campaign are rejected without a window
// and the other statuses are rejected with one: a status whose only effect is
// time-bound weighting is meaningless without a period, and a window on an
// evergreen tag would never be read by anything.
func ResolveDeclaration(rawStatus string, declared *WindowDeclaration) (Status, *Window, error) {
	raw := strings.TrimSpace(rawStatus)
	if raw == "" {
		raw = string(StatusActive)
	}
	status, ok := Parse(raw)
	if !ok {
		return "", nil, fmt.Errorf("unknown lifecycleStatus %q", raw)
	}
	window, err := parseWindow(declared)
	if err != nil {
		return "", nil, err
	}
	switch {
	case RequiresHeatWindow(raw) && window == nil:
		return "", nil, fmt.Errorf("lifecycleStatus %s requires heatWindow", raw)
	case !RequiresHeatWindow(raw) && window != nil:
		return "", nil, fmt.Errorf("lifecycleStatus %s must not declare heatWindow", raw)
	}
	return status, window, nil
}

func parseWindow(declared *WindowDeclaration) (*Window, error) {
	if declared == nil {
		return nil, nil
	}
	startAt, err := time.Parse(time.RFC3339, strings.TrimSpace(declared.StartAt))
	if err != nil {
		return nil, fmt.Errorf("heatWindow.startAt is not RFC3339: %w", err)
	}
	endAt, err := time.Parse(time.RFC3339, strings.TrimSpace(declared.EndAt))
	if err != nil {
		return nil, fmt.Errorf("heatWindow.endAt is not RFC3339: %w", err)
	}
	if !endAt.After(startAt) {
		return nil, fmt.Errorf("heatWindow.endAt must be after startAt")
	}
	recurrence := strings.TrimSpace(declared.Recurrence)
	if recurrence != RecurrenceOnce && recurrence != RecurrenceAnnual {
		return nil, fmt.Errorf("unknown heatWindow.recurrence %q", recurrence)
	}
	return &Window{StartAt: startAt.UTC(), EndAt: endAt.UTC(), Recurrence: recurrence}, nil
}

// CanonicalWindow renders a window for content hashing so that changing only a
// window still produces a new taxonomy release digest.
func CanonicalWindow(window *Window) string {
	if window == nil {
		return ""
	}
	return strings.Join([]string{
		window.StartAt.UTC().Format(time.RFC3339),
		window.EndAt.UTC().Format(time.RFC3339),
		window.Recurrence,
	}, "\x1f")
}

// SameWindow compares two windows by value, treating nil as "no window".
func SameWindow(left, right *Window) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return left.StartAt.Equal(right.StartAt) &&
		left.EndAt.Equal(right.EndAt) &&
		left.Recurrence == right.Recurrence
}

// Status mirrors the TagLifecycleStatus enum in
// quwoquan_service/contracts/metadata/_shared/types.yaml.
type Status string

const (
	// StatusActive is the evergreen default: usable, no heat boost.
	StatusActive Status = "active"
	// StatusTrending is usable and currently boosted by ops or an offline job.
	StatusTrending Status = "trending"
	// StatusSeasonal is usable year-round but only boosted inside its
	// recurring heat window.
	StatusSeasonal Status = "seasonal"
	// StatusCampaign is usable year-round but only boosted inside a one-off
	// heat window tied to a specific campaign.
	StatusCampaign Status = "campaign"
	// StatusDeprecated is the only unusable value: retired from the taxonomy,
	// rejected by resolve, children and validate.
	StatusDeprecated Status = "deprecated"
)

var usableStatuses = []Status{
	StatusActive,
	StatusTrending,
	StatusSeasonal,
	StatusCampaign,
}

// Parse recognizes a stored value. ok is false for anything outside the enum,
// including the empty string.
func Parse(raw string) (Status, bool) {
	switch Status(raw) {
	case StatusActive, StatusTrending, StatusSeasonal, StatusCampaign, StatusDeprecated:
		return Status(raw), true
	default:
		return "", false
	}
}

// IsUsable reports whether a tag may be resolved, listed as a child, validated
// as a writable ref, or used as an intersection anchor.
func IsUsable(raw string) bool {
	status, ok := Parse(raw)
	return ok && status != StatusDeprecated
}

// UsableStatuses returns the storage-filter allowlist. It is a fresh slice so a
// caller handing it to a query builder cannot mutate the vocabulary.
func UsableStatuses() []string {
	return statusStrings(usableStatuses)
}

// AllStatuses returns every declared value, for completeness checks that must
// accept deprecated nodes as validly projected rather than as corrupt rows.
func AllStatuses() []string {
	return append(UsableStatuses(), string(StatusDeprecated))
}

func statusStrings(statuses []Status) []string {
	out := make([]string, 0, len(statuses))
	for _, status := range statuses {
		out = append(out, string(status))
	}
	return out
}

// RequiresHeatWindow reports whether the status is meaningless without a
// window. seasonal and campaign express "hot during a period"; storing them
// without a period leaves the recommendation side with nothing to act on.
func RequiresHeatWindow(raw string) bool {
	status, ok := Parse(raw)
	if !ok {
		return false
	}
	return status == StatusSeasonal || status == StatusCampaign
}
