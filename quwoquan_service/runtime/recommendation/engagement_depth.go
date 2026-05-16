package recommendation

// ContentType identifies the type of content for engagement depth calculation.
type ContentType string

const (
	ContentTypeArticle ContentType = "article"
	ContentTypePhoto   ContentType = "photo"
	ContentTypeVideo   ContentType = "video"
	ContentTypeMoment  ContentType = "moment"
)

// EngagementDepthInput holds the raw signals needed to compute engagement depth.
type EngagementDepthInput struct {
	ContentType ContentType
	// For articles: pages viewed out of total
	PagesViewed int
	TotalPages  int
	// For photo posts: images swiped through
	ImagesViewed int
	TotalImages  int
	// For video: play position vs total duration (milliseconds)
	PlayPositionMs int
	TotalDurationMs int
	// Fallback: raw dwell time for short-content correction
	DwellMs int
}

// ComputeEngagementDepth returns a normalized depth level (0-4) based on content
// type and consumption signals. Short content uses dwell-time-based fallback
// to avoid ratio distortion.
func ComputeEngagementDepth(input EngagementDepthInput) int {
	ratio := computeConsumedRatio(input)
	if ratio < 0 {
		return depthFromDwell(input.DwellMs, input.ContentType)
	}
	return ratioToDepthLevel(ratio)
}

// ComputeConsumedRatio returns the raw consumed ratio (0.0-1.0+) or -1 if
// the input should use dwell-based fallback (short content).
func ComputeConsumedRatio(input EngagementDepthInput) float64 {
	return computeConsumedRatio(input)
}

func computeConsumedRatio(input EngagementDepthInput) float64 {
	switch input.ContentType {
	case ContentTypeArticle:
		if input.TotalPages <= 2 {
			return -1 // use dwell fallback
		}
		if input.TotalPages <= 0 || input.PagesViewed <= 0 {
			return 0
		}
		return float64(input.PagesViewed) / float64(input.TotalPages)

	case ContentTypePhoto:
		if input.TotalImages <= 2 {
			return -1 // use dwell fallback
		}
		if input.TotalImages <= 0 || input.ImagesViewed <= 0 {
			return 0
		}
		return float64(input.ImagesViewed) / float64(input.TotalImages)

	case ContentTypeVideo:
		if input.TotalDurationMs > 0 && input.TotalDurationMs < 10000 {
			// Short video: lower thresholds via adjusted ratio
			if input.PlayPositionMs <= 0 {
				return 0
			}
			raw := float64(input.PlayPositionMs) / float64(input.TotalDurationMs)
			// Boost short video ratios: >50% counts as deep engagement
			return raw * 1.3
		}
		if input.TotalDurationMs <= 0 || input.PlayPositionMs <= 0 {
			return 0
		}
		return float64(input.PlayPositionMs) / float64(input.TotalDurationMs)

	case ContentTypeMoment:
		return -1 // always use dwell fallback for moments

	default:
		return -1
	}
}

// depthFromDwell maps raw dwell time to depth level using content-type-specific
// thresholds. Used when content is too short for ratio-based measurement.
func depthFromDwell(dwellMs int, ct ContentType) int {
	switch ct {
	case ContentTypeArticle:
		// Short article (<=2 pages): <5s→L0, 5-15s→L1, 15-30s→L2, 30s+→L3
		switch {
		case dwellMs < 5000:
			return 0
		case dwellMs < 15000:
			return 1
		case dwellMs < 30000:
			return 2
		default:
			return 3
		}
	case ContentTypePhoto:
		// Short photo post (<=2 images): <3s→L0, 3-8s→L1, 8-15s→L2, 15s+→L3
		switch {
		case dwellMs < 3000:
			return 0
		case dwellMs < 8000:
			return 1
		case dwellMs < 15000:
			return 2
		default:
			return 3
		}
	case ContentTypeMoment:
		// Moments: <2s→L0, 2-5s→L1, 5-10s→L2, 10-20s→L3, 20s+→L4
		switch {
		case dwellMs < 2000:
			return 0
		case dwellMs < 5000:
			return 1
		case dwellMs < 10000:
			return 2
		case dwellMs < 20000:
			return 3
		default:
			return 4
		}
	default:
		// Generic fallback
		switch {
		case dwellMs < 3000:
			return 0
		case dwellMs < 10000:
			return 1
		case dwellMs < 30000:
			return 2
		case dwellMs < 60000:
			return 3
		default:
			return 4
		}
	}
}

// ratioToDepthLevel maps a consumed ratio [0, 1+] to depth level [0, 4].
func ratioToDepthLevel(ratio float64) int {
	switch {
	case ratio < 0.1:
		return 0
	case ratio < 0.3:
		return 1
	case ratio < 0.6:
		return 2
	case ratio < 0.9:
		return 3
	default:
		return 4
	}
}
