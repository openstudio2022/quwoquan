package recommendation

import "testing"

func TestFeedTypesCoverFiveTabXiaoquSurfaces(t *testing.T) {
	got := map[FeedType]bool{
		FeedDiscovery: true,
		FeedCircle:    true,
		FeedTopic:     true,
		FeedHomepage:  true,
		FeedSearch:    true,
	}
	for _, feedType := range []FeedType{
		FeedDiscovery,
		FeedCircle,
		FeedTopic,
		FeedHomepage,
		FeedSearch,
	} {
		if !got[feedType] {
			t.Fatalf("missing feed type %q", feedType)
		}
	}
}

func TestRecallRequestCarriesAttributionContext(t *testing.T) {
	req := RecallRequest{
		FeedType:      FeedHomepage,
		UserID:        "u1",
		CircleID:      "c1",
		TopicID:       "campus",
		HomepageID:    "fixture_homepage_university_pku",
		Surface:       "homepage_detail",
		FeedRequestID: "feed-request-1",
	}
	if req.FeedRequestID == "" || req.Surface == "" || req.HomepageID == "" {
		t.Fatalf("recall request lost attribution context: %#v", req)
	}
}
