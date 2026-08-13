// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
package local_contract

import (
	"context"
	"testing"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	appports "quwoquan_service/services/content-service/internal/content/post/application/ports"
)

// GetGatheringSocialProof 是四锚点两级诚实社会证明的 App 代理读面：
// anchorKind 闭集 organizer/entity/content/creator；计数由 recommendation
// 聚合投影派生，Content 只透传不落副本；reader 未装配 fail-closed。

type fakeSocialProofReader struct {
	summary appports.GatheringSocialProofSummary
	err     error
	calls   int
	anchor  string
	object  string
}

func (r *fakeSocialProofReader) GetGatheringSocialProof(
	_ context.Context,
	anchorKind string,
	objectID string,
) (appports.GatheringSocialProofSummary, error) {
	r.calls++
	r.anchor = anchorKind
	r.object = objectID
	return r.summary, r.err
}

func TestGetGatheringSocialProofRejectsUnknownAnchor(t *testing.T) {
	reader := &fakeSocialProofReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		SocialProof: reader,
	})

	_, err := facade.GetGatheringSocialProof(context.Background(), "rating", "obj-1")

	assertPostQueryErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromInvalidArgument(""),
	)
	if reader.calls != 0 {
		t.Fatalf("unknown anchor must fail before reaching reader")
	}
}

func TestGetGatheringSocialProofFailsClosedWithoutReader(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{})

	_, err := facade.GetGatheringSocialProof(
		context.Background(),
		"organizer",
		"persona-1",
	)

	assertPostQueryErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromRequiredDependencyUnavailable(""),
	)
}

func TestGetGatheringSocialProofPassesThroughHonestCounts(t *testing.T) {
	reader := &fakeSocialProofReader{
		summary: appports.GatheringSocialProofSummary{
			AnchorKind:       "entity",
			ObjectID:         "homepage-1",
			PublishedCount:   3,
			FormedCount:      2,
			ExperiencedCount: 1,
		},
	}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		SocialProof: reader,
	})

	summary, err := facade.GetGatheringSocialProof(
		context.Background(),
		" entity ",
		" homepage-1 ",
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if reader.anchor != "entity" || reader.object != "homepage-1" {
		t.Fatalf("facade must normalize identity before reaching reader")
	}
	if summary.FormedCount != 2 || summary.ExperiencedCount != 1 {
		t.Fatalf("facade must pass counts through untouched: %+v", summary)
	}
}
