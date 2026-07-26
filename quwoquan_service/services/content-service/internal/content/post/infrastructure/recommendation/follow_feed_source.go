package recommendation

import (
	"context"

	rtrec "quwoquan_service/runtime/recommendation"
)

type followFeedGateSource struct {
	source      rtrec.CandidateSource
	allowFollow bool
}

// GateFollowFeedSource 保持关注流 fail-closed：feed route 为 FeedFollow（首页
// following 频道）时，只有关注召回源（AuthorRecallSource）能贡献候选；其他
// feed 类型不受影响。关注为空时候选池为空、feed 返回空列表——绝不混入全量
// 时间流或其他召回内容（B16 收口）。
//
// allowFollow 必须依据"原始未包装源"的类型判定后传入：gate 之间会互相嵌套
// （premium gate 已把源包成值类型），在包装后做类型断言会误伤关注召回。
func GateFollowFeedSource(source rtrec.CandidateSource, allowFollow bool) rtrec.CandidateSource {
	if source == nil {
		return nil
	}
	return followFeedGateSource{source: source, allowFollow: allowFollow}
}

func (s followFeedGateSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if req.FeedType == rtrec.FeedFollow && !s.allowFollow {
		rtrec.RecordFeedGateFiltered("follow_feed", 1)
		return nil, nil
	}
	return s.source.Recall(ctx, req)
}
