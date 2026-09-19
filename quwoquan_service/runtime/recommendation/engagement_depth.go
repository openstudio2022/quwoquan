package recommendation

// EngagementDepthInput holds the raw signals needed to compute engagement depth.
type EngagementDepthInput struct {
	ContentType string
	// For articles: pages viewed out of total
	PagesViewed int
	TotalPages  int
	// For photo posts: images swiped through
	ImagesViewed int
	TotalImages  int
	// For video: play position vs total duration (milliseconds)
	PlayPositionMs  int
	TotalDurationMs int
	// Fallback: raw dwell time for short-content correction
	DwellMs int
}

// ComputeEngagementDepth returns a normalized depth level (0-4) based on content
// type and consumption signals. Short content uses dwell-time-based fallback
// to avoid ratio distortion. Unsupported content types return -1.
func ComputeEngagementDepth(input EngagementDepthInput) int {
	ratio := computeConsumedRatio(input)
	if ratio == -2 {
		return -1 // 不支持的类型不进入有效深度桶。
	}
	if ratio < 0 {
		return depthFromDwell(input.DwellMs, input.ContentType)
	}
	return ratioToDepthLevel(ratio)
}

// ComputeConsumedRatio 返回消费比例；-1 表示短内容使用停留时间，-2 表示类型不支持。
func ComputeConsumedRatio(input EngagementDepthInput) float64 {
	return computeConsumedRatio(input)
}

func computeConsumedRatio(input EngagementDepthInput) float64 {
	switch input.ContentType {
	case "article":
		if input.TotalPages <= 2 {
			return -1 // use dwell fallback
		}
		if input.TotalPages <= 0 || input.PagesViewed <= 0 {
			return 0
		}
		return float64(input.PagesViewed) / float64(input.TotalPages)

	case "image":
		if input.TotalImages <= 2 {
			return -1 // use dwell fallback
		}
		if input.TotalImages <= 0 || input.ImagesViewed <= 0 {
			return 0
		}
		return float64(input.ImagesViewed) / float64(input.TotalImages)

	case "video":
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

	default:
		return -2 // 不支持的类型与短内容回退必须区分。
	}
}

// depthFromDwell maps raw dwell time to depth level using content-type-specific
// thresholds. Used when content is too short for ratio-based measurement.
func depthFromDwell(dwellMs int, ct string) int {
	var thresholds [3]int
	switch ct {
	case "article":
		thresholds = [3]int{5000, 15000, 30000}
	case "image":
		thresholds = [3]int{3000, 8000, 15000}
	default:
		return -1
	}
	for depth, threshold := range thresholds {
		if dwellMs < threshold {
			return depth
		}
	}
	return len(thresholds)
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
