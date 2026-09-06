package homepage

import (
	"context"
	"errors"
	"strings"

	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type QueryFacade struct {
	reader             homepageports.Reader
	details            homepageports.DetailProjectionStore
	followers          homepageports.FollowerProjectionStore
	releaseProjections homepageports.ReleaseProjectionStore
	activeRelease      ActiveReleaseLoader
}

func NewQueryFacade(
	reader homepageports.Reader,
	followers homepageports.FollowerProjectionStore,
) (*QueryFacade, error) {
	if reader == nil {
		return nil, errors.New("homepage query facade requires reader")
	}
	details, ok := reader.(homepageports.DetailProjectionStore)
	if !ok {
		return nil, errors.New("homepage query facade requires detail projection store")
	}
	return &QueryFacade{reader: reader, details: details, followers: followers}, nil
}

// ActiveReleaseLoader is the adaptation seam for the shared runtime/datarelease
// loader. Entity does not own or persist a second active pointer.
type ActiveReleaseLoader interface {
	LoadActiveRelease(ctx context.Context) (homepageports.ReleaseIdentity, bool, error)
}

func (f *QueryFacade) WithReleaseFence(
	projections homepageports.ReleaseProjectionStore,
	active ActiveReleaseLoader,
) *QueryFacade {
	f.releaseProjections = projections
	f.activeRelease = active
	return f
}

func (f *QueryFacade) Get(
	ctx context.Context,
	rawID string,
	viewerPersonaID string,
	includeOffline bool,
) (View, error) {
	snapshot, aggregateFound, err := f.reader.FindExact(ctx, homepageports.ExactLookup{
		ID:          strings.TrimSpace(rawID),
		LookupAlias: homepagemodel.NormalizeLookupAlias(rawID),
	})
	if err != nil {
		return View{}, unavailable(err)
	}
	if aggregateFound && snapshot.Status == homepagemodel.StatusOffline && !includeOffline &&
		(snapshot.SourceOwner != "qwq_data" || f.activeRelease == nil || f.releaseProjections == nil) {
		return View{}, generated.AppErrorFromHomepageOffline("homepage offline")
	}

	var view View
	if aggregateFound {
		view, err = f.detailView(ctx, snapshot)
		if err != nil {
			return View{}, err
		}
	}
	if f.activeRelease != nil && f.releaseProjections != nil {
		identity, activeFound, activeErr := f.activeRelease.LoadActiveRelease(ctx)
		if activeErr != nil {
			return View{}, unavailable(activeErr)
		}
		if !activeFound {
			return View{}, unavailable(errors.New("Content active release fence is absent"))
		}
		if activeFound {
			identity, activeErr = NormalizeReleaseIdentity(identity)
			if activeErr != nil {
				return View{}, unavailable(activeErr)
			}
			projection, projectionFound, projectionErr := f.releaseProjections.LoadExactReleaseProjection(
				ctx, identity, strings.TrimSpace(rawID),
			)
			if projectionErr != nil {
				return View{}, unavailable(projectionErr)
			}
			if projectionFound {
				if !aggregateFound {
					view = ViewFromReleaseProjection(projection)
				} else {
					view = ApplyExactReleaseProjection(view, projection)
				}
				aggregateFound = true
			} else if aggregateFound && snapshot.SourceOwner == "qwq_data" {
				return View{}, generated.AppErrorFromHomepageNotFound("homepage has no exact active release projection")
			}
		} else if aggregateFound && snapshot.SourceOwner == "qwq_data" {
			return View{}, generated.AppErrorFromHomepageNotFound("Content active release fence is absent")
		}
	}
	if !aggregateFound {
		return View{}, generated.AppErrorFromHomepageNotFound("homepage not found")
	}
	if f.followers != nil {
		followerView, followerErr := f.followers.ResolveFollowerView(ctx, view.ID, viewerPersonaID)
		if followerErr != nil {
			return View{}, unavailable(followerErr)
		}
		view.ViewerFollow = ViewerFollowSlice{
			ViewerFollowsHomepage: followerView.ViewerFollows, FollowerCount: followerView.Count,
		}
	}
	return view, nil
}

// FindHomepageStatus 是跨对象写入前的窄读端口。
func (f *QueryFacade) FindHomepageStatus(
	ctx context.Context,
	rawID string,
) (string, bool, error) {
	snapshot, found, err := f.reader.FindExact(ctx, homepageports.ExactLookup{
		ID:          strings.TrimSpace(rawID),
		LookupAlias: homepagemodel.NormalizeLookupAlias(rawID),
	})
	if err != nil || !found {
		return "", found, err
	}
	return string(snapshot.Status), true, nil
}

func (f *QueryFacade) Search(
	ctx context.Context,
	query homepageports.SearchRequestFact,
) (SearchSlice, error) {
	page, err := f.reader.Search(ctx, query)
	if err != nil {
		return SearchSlice{}, unavailable(err)
	}
	result := SearchSlice{NextCursor: page.NextCursor, Items: []SearchItemView{}}
	for _, snapshot := range page.Items {
		view := ViewFromSnapshot(snapshot)
		view, visible, releaseErr := f.applyActiveReleaseProjection(ctx, view)
		if releaseErr != nil {
			return SearchSlice{}, unavailable(releaseErr)
		}
		if !visible {
			continue
		}
		projection, _, projectionErr := f.details.LoadDetailProjection(ctx, snapshot.ID)
		if projectionErr != nil {
			return SearchSlice{}, unavailable(projectionErr)
		}
		coverAssetID, coverAccessMode := detailCoverBinding(
			view.CoverURL,
			view.IntroductionAssets,
		)
		result.Items = append(result.Items, SearchItemView{
			HomepageID:        view.ID,
			CanonicalEntityID: view.CanonicalEntityID,
			Title:             view.Title,
			Subtitle:          view.Subtitle,
			HomepageType:      view.HomepageType,
			CoverURL:          view.CoverURL,
			CoverAssetID:      coverAssetID,
			CoverAccessMode:   coverAccessMode,
			City:              view.City,
			Address:           view.Address,
			Status:            view.Status,
			AverageRating:     cloneFloat(projection.AverageRating),
			RatingCount:       projection.RatingCount,
		})
	}
	return result, nil
}

func (f *QueryFacade) Scan(
	ctx context.Context,
	cursor string,
	limit int,
) ([]View, string, error) {
	page, err := f.reader.Scan(ctx, strings.TrimSpace(cursor), limit)
	if err != nil {
		return nil, "", unavailable(err)
	}
	views := make([]View, 0, len(page.Items))
	for _, snapshot := range page.Items {
		view, detailErr := f.detailView(ctx, snapshot)
		if detailErr != nil {
			return nil, "", detailErr
		}
		views = append(views, view)
	}
	return views, page.NextCursor, nil
}

func (f *QueryFacade) detailView(
	ctx context.Context,
	snapshot homepagemodel.Snapshot,
) (View, error) {
	view := ViewFromSnapshot(snapshot)
	projection, found, err := f.details.LoadDetailProjection(ctx, snapshot.ID)
	if err != nil {
		return View{}, unavailable(err)
	}
	if found {
		view = ApplyDetailProjection(view, projection)
	}
	return view, nil
}

func (f *QueryFacade) Count(ctx context.Context) (int64, error) {
	count, err := f.reader.Count(ctx)
	if err != nil {
		return 0, unavailable(err)
	}
	return count, nil
}

func (f *QueryFacade) applyActiveReleaseProjection(ctx context.Context, view View) (View, bool, error) {
	// No loader means this service instance is still on the pre-release-projection
	// composition. The seam keeps local/manual Homepage behavior available until
	// the shared runtime loader lands; once injected, Data-owned reads fail closed.
	if f.activeRelease == nil || f.releaseProjections == nil {
		return view, true, nil
	}
	// Manual/UGC Homepage rows have no Data identity at all. Legacy Data rows
	// have sourceOwner=qwq_data; newly stage-only stable shells are recognized
	// by an exact active projection and never by governance status.
	dataOwned := view.SourceOwner == "qwq_data"
	identity, found, err := f.activeRelease.LoadActiveRelease(ctx)
	if err != nil {
		return View{}, false, err
	}
	if !found {
		return View{}, false, errors.New("Content active release fence is absent")
	}
	identity, err = NormalizeReleaseIdentity(identity)
	if err != nil {
		return View{}, false, err
	}
	projection, found, err := f.releaseProjections.LoadExactReleaseProjection(ctx, identity, view.ID)
	if err != nil {
		return View{}, false, err
	}
	if !found {
		if dataOwned {
			return View{}, false, nil
		}
		return view, true, nil
	}
	return ApplyExactReleaseProjection(view, projection), true, nil
}
