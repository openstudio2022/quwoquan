package feed

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// effectiveClientPresentationContract 归一本次请求的有效能力声明。整份缺席只
// 落到生成的 MissingDeclaration 固定基线，绝不升级为编译期全能力；任何非空声明
// 都由服务端重算 canonical digest 并与自报值比较，摘要不符即非法入参。
func effectiveClientPresentationContract(
	declared transport.ClientContentPresentationContract,
) (transport.ClientContentPresentationContract, error) {
	if clientPresentationContractAbsent(declared) {
		return transport.MissingDeclarationContentPresentationContract(), nil
	}
	if err := transport.ValidateClientContentPresentationContract(declared); err != nil {
		return transport.ClientContentPresentationContract{},
			contentgenerated.AppErrorFromInvalidArgument(
				"client presentation contract is invalid: " + err.Error(),
			)
	}
	return declared, nil
}

// clientPresentationContractAbsent 只认「整份缺席」。任何一个能力轴或摘要出现
// 就是一份声明，必须整体通过校验，不允许按字段补默认。
func clientPresentationContractAbsent(
	contract transport.ClientContentPresentationContract,
) bool {
	return len(contract.ContentTypes) == 0 &&
		len(contract.ListObjectKinds) == 0 &&
		len(contract.PresentationRecipes) == 0 &&
		len(contract.OpenSurfaces) == 0 &&
		strings.TrimSpace(contract.ContractDigest) == ""
}

func WithRankedRecommendationGateway(
	gateway deliveryapp.RankedRecommendationGateway,
) FeedServiceOption {
	return func(service *FeedService) {
		service.rankedWindows = gateway
	}
}

func WithFeedPageDeliveredPublisher(
	publisher deliveryapp.FeedPageDeliveredPublisher,
) FeedServiceOption {
	return func(service *FeedService) {
		service.deliveryEvents = publisher
	}
}

type rankedRecommendationDelivery struct {
	page      transport.RankedRecommendationPage
	delivered []deliveryapp.DeliveredRecommendationItem
}

// rankedProjectedCandidate 是一条通过能力判定、可以进入扁平 feed 响应的候选。
// 信封判定只做一次，hydrate 与归因复用同一结果。
type rankedProjectedCandidate struct {
	item   transport.RankedRecommendationItem
	postID postports.PostID
}

func (delivery *rankedRecommendationDelivery) bindPage(
	page transport.RankedRecommendationPage,
) error {
	if delivery == nil {
		return deliveryapp.ErrRecommendationUnavailable
	}
	if delivery.page.WindowId == "" {
		delivery.page = page
		return nil
	}
	if delivery.page.WindowId != page.WindowId ||
		delivery.page.Scenario != page.Scenario ||
		delivery.page.ExperimentBucket != page.ExperimentBucket ||
		delivery.page.ModelBucket != page.ModelBucket ||
		delivery.page.PolicyDigest != page.PolicyDigest ||
		delivery.page.ClientPresentationContract.ContractDigest !=
			page.ClientPresentationContract.ContractDigest ||
		delivery.page.RankingSnapshotDigest != page.RankingSnapshotDigest ||
		!delivery.page.FeatureSnapshotAt.Equal(page.FeatureSnapshotAt) ||
		!delivery.page.ExpiresAt.Equal(page.ExpiresAt) {
		return fmt.Errorf(
			"%w: recommendation page attribution changed within one response",
			deliveryapp.ErrRecommendationUnavailable,
		)
	}
	return nil
}

func (delivery *rankedRecommendationDelivery) event(
	deliveryPageID string,
	feedRequestID string,
	subjectID string,
	personaID string,
	occurredAt time.Time,
) deliveryapp.FeedPageDelivered {
	return deliveryapp.FeedPageDelivered{
		DeliveryPageID:        deliveryPageID,
		FeedRequestID:         feedRequestID,
		SubjectID:             subjectID,
		PersonaID:             personaID,
		Scenario:              delivery.page.Scenario,
		WindowID:              delivery.page.WindowId,
		ExperimentBucket:      delivery.page.ExperimentBucket,
		ModelBucket:           delivery.page.ModelBucket,
		ModelChannel:          delivery.page.ModelChannel,
		ModelReleaseID:        delivery.page.ModelReleaseId,
		RankingSnapshotDigest: delivery.page.RankingSnapshotDigest,
		FeatureSnapshotAt:     delivery.page.FeatureSnapshotAt,
		UserFeatureSnapshot:   cloneSnapshot(delivery.page.UserFeatureSnapshot),
		Items:                 append([]deliveryapp.DeliveredRecommendationItem(nil), delivery.delivered...),
		OccurredAt:            occurredAt,
	}
}

func recommendationScenario(route feedRoute) string {
	switch {
	case route.FeedType == rtrec.FeedFollow:
		return "following"
	case route.Surface == "premium_stream":
		return "premium_stream"
	case route.Vertical == "travel_photography":
		return "travel_photography"
	default:
		return "content_feed"
	}
}

func rankedRecommendationSubject(req ListFeedRequest, route feedRoute) string {
	if route.FeedType == rtrec.FeedFollow {
		return strings.TrimSpace(req.ViewerPersonaID)
	}
	if !identity.IsAnonymousFallbackPersonaID(req.UserID) {
		return strings.TrimSpace(req.UserID)
	}
	return identity.RankedFeedWindowSubjectID(req.UserID, req.SessionID)
}

func (s *FeedService) rankedRecommendationPage(
	ctx context.Context,
	req ListFeedRequest,
	route feedRoute,
	feedRequestID string,
	continuation *rtrec.RankedFeedContinuation,
	limit int,
	supply ActiveSupplySnapshot,
) (transport.RankedRecommendationPage, error) {
	if s == nil || s.rankedWindows == nil {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	fence := transport.ReleasePinnedQueryFence{}
	if !supply.IsEmpty() {
		if !supply.ReleaseBoundReadbackReady() {
			return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
		}
		fence.Release = &transport.ReleaseCandidateBinding{Environment: supply.Environment, SourceOwner: supply.SourceOwner, ReleaseId: supply.ActiveReleaseID, ManifestDigest: supply.ManifestDigest}
		fence.Revision = supply.Revision
	}
	scenario := recommendationScenario(route)
	// 建窗与续页必须携带同一份有效能力声明：窗口的候选闭集按它裁剪，
	// 缺席会让 recommendation 侧退回固定基线，与首刷不再是同一个窗口。
	contract := req.ClientPresentationContract
	var (
		page transport.RankedRecommendationPage
		err  error
	)
	if continuation == nil {
		page, err = s.rankedWindows.Create(
			ctx,
			transport.CreateRankedRecommendationWindowCommand{
				ContentFence:               fence,
				IdempotencyKey:             strings.TrimSpace(feedRequestID),
				SubjectId:                  rankedRecommendationSubject(req, route),
				Scenario:                   scenario,
				ClientPresentationContract: contract,
				Limit:                      limit,
			},
		)
	} else {
		fromOrdinal := continuation.AfterOrdinal
		pageLimit := limit
		page, err = s.rankedWindows.GetPage(
			ctx,
			transport.GetRankedRecommendationPageQuery{
				ContentFence:               fence,
				SubjectId:                  rankedRecommendationSubject(req, route),
				WindowId:                   strings.TrimSpace(continuation.WindowID),
				ClientPresentationContract: contract,
				FromOrdinal:                &fromOrdinal,
				Limit:                      &pageLimit,
			},
		)
	}
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	// 窗口回显的能力必须与本次请求发出的完全一致：digest 由服务端重算，
	// 不等即说明窗口绑定的能力与当前请求不是同一份，旧游标必须被弃用。
	if presentationErr := assertWindowPresentationContract(
		page.ClientPresentationContract,
		contract,
	); presentationErr != nil {
		return transport.RankedRecommendationPage{}, presentationErr
	}
	if page.ContentFence.Revision != fence.Revision || (page.ContentFence.Release == nil) != (fence.Release == nil) || (fence.Release != nil && *page.ContentFence.Release != *fence.Release) {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	if page.Scenario != scenario ||
		(continuation != nil && page.WindowId != strings.TrimSpace(continuation.WindowID)) {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: recommendation continuation binding changed",
			deliveryapp.ErrRecommendationUnavailable,
		)
	}
	return page, nil
}

// assertWindowPresentationContract 比对窗口回显能力与请求发出的能力。回显值
// 自身必须通过 canonical digest 重算，任何摘要差异都是「能力已变化」而不是
// 非法入参：调用方必须弃用旧游标从首屏重来。
func assertWindowPresentationContract(
	echoed transport.ClientContentPresentationContract,
	sent transport.ClientContentPresentationContract,
) error {
	if err := transport.ValidateClientContentPresentationContract(echoed); err != nil {
		return contentgenerated.AppErrorFromPresentationContractChanged(
			"ranked window echoed an unverifiable client presentation contract: " + err.Error(),
		)
	}
	if echoed.ContractDigest != sent.ContractDigest {
		return contentgenerated.AppErrorFromPresentationContractChanged(fmt.Sprintf(
			"ranked window is bound to presentation contract %s but the request declares %s",
			echoed.ContractDigest,
			sent.ContractDigest,
		))
	}
	return nil
}

// rankedItemProjection 判定这一条窗口条目在当前 feed 响应里的归宿，三种结果
// 互斥：可投影（返回 Post 身份）、超出本次请求声明的能力（窗口没有遵守建窗
// 契约，fail-closed）、以及能力内但当前扁平响应形状投不出（可过滤，由调用方
// 按预算补足并给出终态）。不得按 post 猜测，也不得静默丢弃后重排序位。
func rankedItemProjection(
	item transport.RankedRecommendationItem,
	contract transport.ClientContentPresentationContract,
) (postports.PostID, bool, error) {
	envelope := item.Envelope
	if envelope.ObjectKind.Validate() != nil || envelope.OpenSurface.Validate() != nil {
		return "", false, fmt.Errorf(
			"%w: ranked recommendation item ordinal %d declares an invalid presentation envelope",
			deliveryapp.ErrRecommendationUnavailable,
			item.Ordinal,
		)
	}
	if !declaredBy(contract.ListObjectKinds, envelope.ObjectKind) ||
		!declaredBy(contract.OpenSurfaces, envelope.OpenSurface) ||
		(envelope.ContentType != nil &&
			!declaredBy(contract.ContentTypes, *envelope.ContentType)) ||
		(envelope.PresentationRecipe != nil &&
			!declaredBy(contract.PresentationRecipes, *envelope.PresentationRecipe)) {
		return "", false, fmt.Errorf(
			"%w: ranked recommendation item ordinal %d is outside presentation contract %s",
			deliveryapp.ErrRecommendationUnavailable,
			item.Ordinal,
			contract.ContractDigest,
		)
	}
	if envelope.ObjectKind != transport.ListObjectKindPost {
		// 能力内但 Content 当前只能投影 post 项：混排信封是另一条收口，
		// 这里只报告「投不出」，由调用方补足或给出终态。
		return "", false, nil
	}
	if envelope.Post == nil {
		return "", false, fmt.Errorf(
			"%w: ranked recommendation item ordinal %d declares objectKind post without a post reference",
			deliveryapp.ErrRecommendationUnavailable,
			item.Ordinal,
		)
	}
	postID := postports.NewPostID(envelope.Post.PostId)
	if postID == "" {
		return "", false, fmt.Errorf(
			"%w: ranked recommendation item ordinal %d carries an empty postId",
			deliveryapp.ErrRecommendationUnavailable,
			item.Ordinal,
		)
	}
	return postID, true, nil
}

func declaredBy[member comparable](declared []member, value member) bool {
	for _, candidate := range declared {
		if candidate == value {
			return true
		}
	}
	return false
}

func rankedFeedItem(item transport.RankedRecommendationItem, postID postports.PostID) rtrec.FeedItem {
	return rtrec.FeedItem{
		ContentID:       string(postID),
		Score:           item.Score,
		QualityScore:    item.Score,
		RecallPath:      snapshotText(item.ItemFeatureSnapshot, "recallPath"),
		ContentVertical: snapshotText(item.ItemFeatureSnapshot, "contentVertical"),
		SupplySource:    snapshotText(item.ItemFeatureSnapshot, "supplySource"),
	}
}

func snapshotText(snapshot map[string]any, key string) string {
	value, ok := snapshot[key]
	if !ok || value == nil {
		return ""
	}
	text, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(text)
}

func rankedContinuation(
	page transport.RankedRecommendationPage,
) *rtrec.RankedFeedContinuation {
	if page.NextOrdinal == nil {
		return nil
	}
	afterContentID := ""
	if last := len(page.Items) - 1; last >= 0 {
		if reference := page.Items[last].Envelope.Post; reference != nil {
			afterContentID = strings.TrimSpace(reference.PostId)
		}
	}
	return &rtrec.RankedFeedContinuation{
		WindowID:       strings.TrimSpace(page.WindowId),
		AfterOrdinal:   *page.NextOrdinal,
		AfterContentID: afterContentID,
		ExpiresAt:      page.ExpiresAt.UTC(),
	}
}

func deliveredRecommendationItem(
	item transport.RankedRecommendationItem,
	postID postports.PostID,
	view FeedItemView,
) deliveryapp.DeliveredRecommendationItem {
	return deliveryapp.DeliveredRecommendationItem{
		Ordinal:               item.Ordinal,
		ContentID:             string(postID),
		ContentType:           strings.TrimSpace(view.ContentType),
		FeatureSnapshotDigest: strings.TrimSpace(item.FeatureSnapshotDigest),
		ItemFeatureSnapshot:   cloneSnapshot(item.ItemFeatureSnapshot),
	}
}

func cloneSnapshot(source map[string]any) map[string]any {
	clone := make(map[string]any, len(source))
	for key, value := range source {
		clone[key] = value
	}
	return clone
}
