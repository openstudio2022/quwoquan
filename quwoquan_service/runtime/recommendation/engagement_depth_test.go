package recommendation

import "testing"

func TestComputeEngagementDepth_Article_Normal(t *testing.T) {
	tests := []struct {
		name        string
		pages       int
		total       int
		wantDepth   int
	}{
		{"0/8 pages = L0", 0, 8, 0},
		{"1/8 pages = L1", 1, 8, 1},
		{"2/8 pages = L1", 2, 8, 1},
		{"3/8 pages = L2", 3, 8, 2},
		{"6/8 pages = L3", 6, 8, 3},
		{"8/8 pages = L4", 8, 8, 4},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ComputeEngagementDepth(EngagementDepthInput{
				ContentType: ContentTypeArticle,
				PagesViewed: tt.pages,
				TotalPages:  tt.total,
			})
			if got != tt.wantDepth {
				t.Errorf("got depth %d, want %d", got, tt.wantDepth)
			}
		})
	}
}

func TestComputeEngagementDepth_Article_ShortFallback(t *testing.T) {
	tests := []struct {
		name      string
		dwellMs   int
		wantDepth int
	}{
		{"<5s = L0", 3000, 0},
		{"8s = L1", 8000, 1},
		{"20s = L2", 20000, 2},
		{"45s = L3", 45000, 3},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ComputeEngagementDepth(EngagementDepthInput{
				ContentType: ContentTypeArticle,
				TotalPages:  2, // short article triggers dwell fallback
				PagesViewed: 1,
				DwellMs:     tt.dwellMs,
			})
			if got != tt.wantDepth {
				t.Errorf("got depth %d, want %d", got, tt.wantDepth)
			}
		})
	}
}

func TestComputeEngagementDepth_Photo_Normal(t *testing.T) {
	tests := []struct {
		name      string
		viewed    int
		total     int
		wantDepth int
	}{
		{"0/9 images = L0", 0, 9, 0},
		{"1/9 images = L1", 1, 9, 1},
		{"2/9 images = L1", 2, 9, 1},
		{"5/9 images = L2", 5, 9, 2},
		{"7/9 images = L3", 7, 9, 3},
		{"9/9 images = L4", 9, 9, 4},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ComputeEngagementDepth(EngagementDepthInput{
				ContentType:  ContentTypePhoto,
				ImagesViewed: tt.viewed,
				TotalImages:  tt.total,
			})
			if got != tt.wantDepth {
				t.Errorf("got depth %d, want %d", got, tt.wantDepth)
			}
		})
	}
}

func TestComputeEngagementDepth_Photo_ShortFallback(t *testing.T) {
	got := ComputeEngagementDepth(EngagementDepthInput{
		ContentType:  ContentTypePhoto,
		TotalImages:  2, // short → dwell fallback
		ImagesViewed: 1,
		DwellMs:      10000,
	})
	if got != 2 {
		t.Errorf("got depth %d, want 2 (8-15s range for short photo)", got)
	}
}

func TestComputeEngagementDepth_Video_Normal(t *testing.T) {
	tests := []struct {
		name      string
		posMs     int
		totalMs   int
		wantDepth int
	}{
		{"5% = L0", 3000, 60000, 0},
		{"25% = L1", 15000, 60000, 1},
		{"50% = L2", 30000, 60000, 2},
		{"75% = L3", 45000, 60000, 3},
		{"95% = L4", 57000, 60000, 4},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ComputeEngagementDepth(EngagementDepthInput{
				ContentType:     ContentTypeVideo,
				PlayPositionMs:  tt.posMs,
				TotalDurationMs: tt.totalMs,
			})
			if got != tt.wantDepth {
				t.Errorf("got depth %d, want %d", got, tt.wantDepth)
			}
		})
	}
}

func TestComputeEngagementDepth_Video_Short(t *testing.T) {
	// Short video (8s): 60% watched → boosted ratio 0.78 → L3
	got := ComputeEngagementDepth(EngagementDepthInput{
		ContentType:     ContentTypeVideo,
		PlayPositionMs:  4800,
		TotalDurationMs: 8000,
	})
	if got != 3 {
		t.Errorf("short video 60%% watched: got depth %d, want 3", got)
	}

	// Short video: full watch → boosted ratio 1.3 → L4
	got = ComputeEngagementDepth(EngagementDepthInput{
		ContentType:     ContentTypeVideo,
		PlayPositionMs:  8000,
		TotalDurationMs: 8000,
	})
	if got != 4 {
		t.Errorf("short video 100%% watched: got depth %d, want 4", got)
	}
}

func TestComputeEngagementDepth_Moment(t *testing.T) {
	tests := []struct {
		name      string
		dwellMs   int
		wantDepth int
	}{
		{"1s = L0", 1000, 0},
		{"3s = L1", 3000, 1},
		{"7s = L2", 7000, 2},
		{"15s = L3", 15000, 3},
		{"25s = L4", 25000, 4},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ComputeEngagementDepth(EngagementDepthInput{
				ContentType: ContentTypeMoment,
				DwellMs:     tt.dwellMs,
			})
			if got != tt.wantDepth {
				t.Errorf("got depth %d, want %d", got, tt.wantDepth)
			}
		})
	}
}
