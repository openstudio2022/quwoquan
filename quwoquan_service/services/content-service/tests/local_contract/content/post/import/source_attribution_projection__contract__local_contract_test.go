package releaseimport_test

import (
	"path/filepath"
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestLoadArticlePreservesCompleteSourceAttribution(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/article/攻略/都江堰/1/manifest.json"),
		`{
			"contentType":"article",
			"contentIdentity":"work",
			"entityRefs":["地点/景区/都江堰"],
			"tagRefs":[],
			"publishTitle":"都江堰",
			"publishAngle":"攻略",
			"publishSeq":1,
			"publishedAt":"2026-08-11T01:02:03Z",
			"sourceAttribution":{
				"isOriginal":false,
				"originalCreatorId":"creator-1",
				"originalCreatorName":"摄影师甲",
				"originalCreatorProfileUrl":"https://media.example/creators/creator-1",
				"platform":"Wikimedia Commons",
				"sourcePostUrl":"https://media.example/posts/dujiangyan",
				"originalAssetUrl":"https://media.example/assets/dujiangyan.jpg",
				"attributionText":"摄影师甲 / CC BY-SA 4.0",
				"rightsBasis":"CC BY-SA 4.0",
				"commercialAuthorizationStatus":"verified",
				"publicationAdmission":"commercial_release",
				"authorizationProofUrl":"https://media.example/proofs/dujiangyan",
				"termsUrl":"https://creativecommons.org/licenses/by-sa/4.0/",
				"riskAcceptanceId":"",
				"watermarkStatus":"absent",
				"audioRightsStatus":"no_audio",
				"modelReleaseStatus":"not_required",
				"propertyReleaseStatus":"not_required",
				"collectedAt":"2026-08-11T00:00:00Z",
				"takedownPolicy":"quwoquan_standard_notice_and_takedown"
			}
		}`,
	)

	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("want one article post, got %d", len(posts))
	}
	got := posts[0].SourceAttribution
	if got.IsOriginal ||
		got.OriginalCreatorId != "creator-1" ||
		got.OriginalCreatorName != "摄影师甲" ||
		got.OriginalCreatorProfileUrl != "https://media.example/creators/creator-1" ||
		got.Platform != "Wikimedia Commons" ||
		got.SourcePostUrl != "https://media.example/posts/dujiangyan" ||
		got.OriginalAssetUrl != "https://media.example/assets/dujiangyan.jpg" ||
		got.AttributionText != "摄影师甲 / CC BY-SA 4.0" ||
		got.RightsBasis != "CC BY-SA 4.0" ||
		got.CommercialAuthorizationStatus != "verified" ||
		got.PublicationAdmission != "commercial_release" ||
		got.AuthorizationProofUrl != "https://media.example/proofs/dujiangyan" ||
		got.TermsUrl != "https://creativecommons.org/licenses/by-sa/4.0/" ||
		got.WatermarkStatus != "absent" ||
		got.AudioRightsStatus != "no_audio" ||
		got.ModelReleaseStatus != "not_required" ||
		got.PropertyReleaseStatus != "not_required" ||
		got.CollectedAt.UTC().Format("2006-01-02T15:04:05Z") != "2026-08-11T00:00:00Z" ||
		got.TakedownPolicy != "quwoquan_standard_notice_and_takedown" {
		t.Fatalf("complete sourceAttribution drifted: %#v", got)
	}
}
