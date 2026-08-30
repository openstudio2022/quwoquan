package feed

import (
	"context"
	"errors"
	"strings"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func WithFeedDeliveryPageStore(store deliveryapp.Store) FeedServiceOption {
	return func(service *FeedService) {
		service.deliveryPages = store
	}
}

type feedDeliveryPageReplay struct {
	items               []FeedItemView
	objectCards         []ObjectCardView
	nextCursor          string
	previousCursor      string
	paginationExpiresAt time.Time
	feedRequestID       string
	policyDigest        string
	experimentBucket    string
	// releaseID/manifestDigest 回放页绑定的内容激活身份；continuation 页
	// 必须携带首刷时冻结的同一 release 身份。
	releaseID      string
	manifestDigest string
}

type feedDeliveryPageAppendInput struct {
	scope            string
	deliveryPageID   string
	feedRequestID    string
	pageSize         int
	depth            int
	previousPageID   string
	items            []FeedItemView
	objectCards      []ObjectCardView
	outboundCursor   string
	releaseID        string
	manifestDigest   string
	policyDigest     string
	experimentBucket string
	createdAt        time.Time
	expiresAt        time.Time
}

func newFeedDeliveryPageIdentity(now time.Time) (string, time.Time, error) {
	pageID, err := deliverymodel.NewID()
	if err != nil {
		return "", time.Time{}, err
	}
	return pageID, now.UTC().Add(deliverymodel.TTL), nil
}

func (s *FeedService) appendFeedDeliveryPage(
	ctx context.Context,
	input feedDeliveryPageAppendInput,
) error {
	if s == nil || s.deliveryPages == nil {
		return deliveryapp.ErrStoreUnavailable
	}
	_, err := s.deliveryPages.Append(ctx, deliverymodel.Page{
		DeliveryPageID:   input.deliveryPageID,
		ScopeHash:        deliverymodel.ScopeHash(input.scope),
		FeedRequestID:    input.feedRequestID,
		PageSize:         input.pageSize,
		Depth:            input.depth,
		PreviousPageID:   input.previousPageID,
		Items:            deliveryPageReferences(input.items),
		ObjectCards:      deliveryPageObjectCards(input.objectCards),
		OutboundCursor:   input.outboundCursor,
		ReleaseID:        input.releaseID,
		ManifestDigest:   input.manifestDigest,
		PolicyDigest:     input.policyDigest,
		ExperimentBucket: input.experimentBucket,
		CreatedAt:        input.createdAt.UTC(),
		ExpiresAt:        input.expiresAt.UTC(),
	})
	return err
}

func (s *FeedService) previousCursorFromInbound(
	scope string,
	state feedCursorEnvelope,
) (string, time.Time, error) {
	pageID := strings.TrimSpace(state.DeliveryPageID)
	if pageID == "" || state.DeliveryPageExpiresAt <= s.cursorCodec.now().UnixMilli() {
		return "", time.Time{}, nil
	}
	expiresAt := time.UnixMilli(state.DeliveryPageExpiresAt).UTC()
	depth := state.Depth - 1
	if depth < 0 {
		depth = 0
	}
	encoded, err := s.cursorCodec.encode(feedCursorEnvelope{
		Kind:                  feedCursorKindDeliveryPage,
		DeliveryPageID:        pageID,
		DeliveryPageExpiresAt: state.DeliveryPageExpiresAt,
		FeedRequestID:         strings.TrimSpace(state.FeedRequestID),
		ReleaseID:             strings.TrimSpace(state.ReleaseID),
		ManifestDigest:        strings.TrimSpace(state.ManifestDigest),
		Depth:                 depth,
		ExpiresAt:             state.DeliveryPageExpiresAt,
	}, scope)
	return encoded, expiresAt, err
}

func (s *FeedService) replayFeedDeliveryPage(
	ctx context.Context,
	req ListFeedRequest,
	route feedRoute,
	requestedIdentity string,
	requestedType string,
	cursorState feedCursorEnvelope,
	appendPost func(*postports.PostFeedItemSlice, *rtrec.FeedItem) bool,
	currentItems func() []FeedItemView,
) (feedDeliveryPageReplay, error) {
	if s == nil || s.deliveryPages == nil || s.postReader == nil {
		return feedDeliveryPageReplay{}, deliveryapp.ErrStoreUnavailable
	}
	scope := feedCursorScope(req, route, requestedIdentity, requestedType)
	scopeHash := deliverymodel.ScopeHash(scope)
	page, err := s.deliveryPages.Load(ctx, scopeHash, cursorState.DeliveryPageID)
	if err != nil {
		return feedDeliveryPageReplay{}, err
	}
	if page.PageSize != NormalizeFeedLimit(req.Limit) ||
		page.FeedRequestID != strings.TrimSpace(cursorState.FeedRequestID) ||
		page.Depth != cursorState.Depth ||
		page.ExpiresAt.UnixMilli() != cursorState.DeliveryPageExpiresAt ||
		page.ReleaseID != strings.TrimSpace(cursorState.ReleaseID) ||
		page.ManifestDigest != strings.TrimSpace(cursorState.ManifestDigest) {
		return feedDeliveryPageReplay{}, deliveryapp.ErrNotFound
	}
	postIDs := make([]postports.PostID, 0, len(page.Items))
	for _, item := range page.Items {
		postIDs = append(postIDs, postports.NewPostID(item.PostID))
	}
	postsByID, readErr := s.postReader.FindPublishedFeedPosts(
		ctx,
		postports.NewPostFeedHydrationRequest(
			postIDs,
			page.ReleaseID,
			page.ManifestDigest,
		),
	)
	if readErr != nil {
		return feedDeliveryPageReplay{}, storageReadFailure(
			"hydrate delivered feed page",
			readErr,
		)
	}
	for _, reference := range page.Items {
		post, ok := postsByID[postports.NewPostID(reference.PostID)]
		if !ok || !feedDeliveryReleaseMatches(
			&post,
			page.ReleaseID,
			page.ManifestDigest,
		) {
			continue
		}
		appendPost(&post, &rtrec.FeedItem{
			ContentID:       reference.PostID,
			QualityScore:    reference.QualityScore,
			RecallPath:      reference.RecallPath,
			ContentVertical: reference.ContentVertical,
			SupplySource:    reference.SupplySource,
		})
	}
	items := append([]FeedItemView(nil), currentItems()...)
	if s.intersections != nil && strings.TrimSpace(req.UserID) != "" {
		if reasons, reasonErr := s.intersections.Feed(
			ctx,
			req.UserID,
			route.ChannelID,
			feedIntersectionPoolLimit,
		); reasonErr == nil {
			AttachFeedIntersections(items, reasons, req.UserID)
		}
	}
	previousCursor, previousExpiry, err := s.previousDeliveryPageCursor(
		ctx,
		scope,
		scopeHash,
		page,
	)
	if err != nil {
		return feedDeliveryPageReplay{}, err
	}
	nextCursor := strings.TrimSpace(page.OutboundCursor)
	nextExpiry := time.Time{}
	if page.OutboundCursor != "" {
		state, decodeErr := s.cursorCodec.decodeSealed(
			page.OutboundCursor,
			scope,
			true,
		)
		if decodeErr != nil ||
			state.FeedRequestID != page.FeedRequestID ||
			state.Depth != page.Depth+1 ||
			state.DeliveryPageID != page.DeliveryPageID ||
			state.DeliveryPageExpiresAt != page.ExpiresAt.UnixMilli() {
			return feedDeliveryPageReplay{}, deliveryapp.ErrNotFound
		}
		if state.ExpiresAt <= s.cursorCodec.now().UnixMilli() {
			nextCursor = ""
		} else {
			nextExpiry = earlierTime(
				page.ExpiresAt,
				time.UnixMilli(state.ExpiresAt).UTC(),
			)
		}
	}
	paginationExpiry := earlierTime(nextExpiry, previousExpiry)
	return feedDeliveryPageReplay{
		items:               items,
		objectCards:         rebaseDeliveredObjectCards(page, items),
		nextCursor:          nextCursor,
		previousCursor:      previousCursor,
		paginationExpiresAt: paginationExpiry,
		feedRequestID:       page.FeedRequestID,
		policyDigest:        page.PolicyDigest,
		experimentBucket:    page.ExperimentBucket,
		releaseID:           page.ReleaseID,
		manifestDigest:      page.ManifestDigest,
	}, nil
}

func (s *FeedService) previousDeliveryPageCursor(
	ctx context.Context,
	scope string,
	scopeHash string,
	page deliverymodel.Page,
) (string, time.Time, error) {
	if strings.TrimSpace(page.PreviousPageID) == "" {
		return "", time.Time{}, nil
	}
	previous, err := s.deliveryPages.Load(ctx, scopeHash, page.PreviousPageID)
	if errors.Is(err, deliveryapp.ErrNotFound) {
		return "", time.Time{}, nil
	}
	if err != nil {
		return "", time.Time{}, err
	}
	if previous.Depth != page.Depth-1 ||
		previous.FeedRequestID != page.FeedRequestID ||
		previous.ReleaseID != page.ReleaseID ||
		previous.ManifestDigest != page.ManifestDigest {
		return "", time.Time{}, deliveryapp.ErrNotFound
	}
	encoded, err := s.cursorCodec.encode(feedCursorEnvelope{
		Kind:                  feedCursorKindDeliveryPage,
		DeliveryPageID:        previous.DeliveryPageID,
		DeliveryPageExpiresAt: previous.ExpiresAt.UnixMilli(),
		FeedRequestID:         previous.FeedRequestID,
		ReleaseID:             previous.ReleaseID,
		ManifestDigest:        previous.ManifestDigest,
		Depth:                 previous.Depth,
		ExpiresAt:             previous.ExpiresAt.UnixMilli(),
	}, scope)
	if err != nil {
		return "", time.Time{}, err
	}
	return encoded, previous.ExpiresAt, nil
}

func feedDeliveryReleaseMatches(
	post *postports.PostFeedItemSlice,
	releaseID string,
	manifestDigest string,
) bool {
	if post == nil {
		return false
	}
	releaseID = strings.TrimSpace(releaseID)
	manifestDigest = strings.TrimSpace(manifestDigest)
	if releaseID == "" && manifestDigest == "" {
		return true
	}
	return strings.TrimSpace(post.ReleaseID) == releaseID &&
		strings.TrimSpace(post.ManifestDigest) == manifestDigest &&
		strings.TrimSpace(post.LifecycleStatus) == "active"
}

func rebaseDeliveredObjectCards(
	page deliverymodel.Page,
	visible []FeedItemView,
) []ObjectCardView {
	if len(page.ObjectCards) == 0 || len(visible) == 0 {
		return nil
	}
	visibleIDs := make(map[string]struct{}, len(visible))
	for _, item := range visible {
		visibleIDs[item.PostID] = struct{}{}
	}
	cards := make([]ObjectCardView, 0, len(page.ObjectCards))
	for _, card := range page.ObjectCards {
		originalAnchor := card.AnchorIndex
		if originalAnchor > len(page.Items) {
			originalAnchor = len(page.Items)
		}
		visibleAnchor := 0
		for _, item := range page.Items[:originalAnchor] {
			if _, ok := visibleIDs[item.PostID]; ok {
				visibleAnchor++
			}
		}
		cards = append(cards, ObjectCardView{
			ObjectKind:  card.ObjectKind,
			ObjectID:    card.ObjectID,
			Title:       card.Title,
			Subtitle:    card.Subtitle,
			CoverURL:    card.CoverURL,
			TagRefs:     append([]string(nil), card.TagRefs...),
			ReasonText:  card.ReasonText,
			RecallPath:  card.RecallPath,
			AnchorIndex: visibleAnchor,
		})
	}
	return cards
}

func deliveryPageReferences(items []FeedItemView) []deliverymodel.PostReference {
	references := make([]deliverymodel.PostReference, 0, len(items))
	for _, item := range items {
		references = append(references, deliverymodel.PostReference{
			PostID:          item.PostID,
			QualityScore:    item.QualityScore,
			RecallPath:      item.RecallPath,
			ContentVertical: item.ContentVertical,
			SupplySource:    item.SupplySource,
		})
	}
	return references
}

func deliveryPageObjectCards(cards []ObjectCardView) []deliverymodel.ObjectCard {
	output := make([]deliverymodel.ObjectCard, 0, len(cards))
	for _, card := range cards {
		output = append(output, deliverymodel.ObjectCard{
			ObjectKind:  card.ObjectKind,
			ObjectID:    card.ObjectID,
			Title:       card.Title,
			Subtitle:    card.Subtitle,
			CoverURL:    card.CoverURL,
			TagRefs:     append([]string(nil), card.TagRefs...),
			ReasonText:  card.ReasonText,
			RecallPath:  card.RecallPath,
			AnchorIndex: card.AnchorIndex,
		})
	}
	return output
}

func earlierTime(left time.Time, right time.Time) time.Time {
	if left.IsZero() || (!right.IsZero() && right.Before(left)) {
		return right
	}
	return left
}

func paginationExpiryWire(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano)
}
