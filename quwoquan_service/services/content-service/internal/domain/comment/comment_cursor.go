package comment

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"time"
)

// CursorPhase distinguishes the two-segment top-level listing (pinned-first then
// the main/unpinned segment) from flat single-segment listings (replies / author
// feeds). It is part of the keyset cursor so a page can resume in the correct
// segment without re-scanning.
type CursorPhase string

const (
	// PhasePinned: the next page continues inside the pinned segment.
	PhasePinned CursorPhase = "pinned"
	// PhaseMain: the next page continues inside the non-pinned (ranked) segment.
	PhaseMain CursorPhase = "main"
	// PhaseFlat: single-segment listing (replies / author / received).
	PhaseFlat CursorPhase = "flat"
)

// Cursor is the strongly-typed keyset pagination cursor (R04: no map[string]any).
// It encodes the sort-key tuple of the previous page's last row so the next page
// can index-seek strictly after it — eliminating offset/1e4-scan truncation and
// recommended/most_liked pagination drift. The immutable (createdAt, _id) suffix
// is always present and guarantees a total order even when the mutable score key
// is unchanged within a browsing session.
type Cursor struct {
	// Phase selects the segment to resume in (pinned/main for top-level, flat
	// otherwise). For PhaseMain with an empty ID, the main segment starts from
	// the top (used when the pinned segment was exactly exhausted).
	Phase CursorPhase `json:"p"`
	// HasScore reports whether Score participates in the keyset (recommended /
	// most_liked). When false the keyset is (TimeUnixNano, ID) only.
	HasScore bool `json:"h,omitempty"`
	// Score is the mode key snapshot: recommendedScore (recommended) or
	// likeCount-as-float (most_liked).
	Score float64 `json:"s,omitempty"`
	// TimeUnixNano carries pinnedAt (PhasePinned) or createdAt (main/flat) of
	// the last returned row, in unix nanoseconds.
	TimeUnixNano int64 `json:"t"`
	// ID is the last returned row's _id, the deterministic final tiebreak.
	ID string `json:"i"`
}

// KeyTime returns the cursor's key time as a UTC time.Time.
func (c Cursor) KeyTime() time.Time {
	return time.Unix(0, c.TimeUnixNano).UTC()
}

// EncodeCursor renders a cursor as an opaque URL-safe base64 token. A zero-value
// cursor or marshal failure encodes to the empty string ("no next page").
func EncodeCursor(c Cursor) string {
	if c.ID == "" && c.Phase != PhaseMain {
		return ""
	}
	raw, err := json.Marshal(c)
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

// DecodeCursor parses an opaque cursor token. It reports ok=false for empty or
// malformed input so callers fall back to a from-the-top read instead of erroring
// on a stale/garbage cursor.
func DecodeCursor(token string) (Cursor, bool) {
	token = strings.TrimSpace(token)
	if token == "" {
		return Cursor{}, false
	}
	raw, err := base64.RawURLEncoding.DecodeString(token)
	if err != nil {
		return Cursor{}, false
	}
	var c Cursor
	if err := json.Unmarshal(raw, &c); err != nil {
		return Cursor{}, false
	}
	if c.Phase == "" {
		return Cursor{}, false
	}
	return c, true
}
