package homepage

import (
	"context"
	"errors"
	"strings"

	homepagemodel "quwoquan_service/services/entity-service/internal/domain/homepage/model"
	homepageports "quwoquan_service/services/entity-service/internal/domain/homepage/ports"
	"quwoquan_service/services/entity-service/internal/generated"
)

type QueryFacade struct {
	reader    homepageports.Reader
	followers homepageports.FollowerProjectionStore
}

func NewQueryFacade(
	reader homepageports.Reader,
	followers homepageports.FollowerProjectionStore,
) (*QueryFacade, error) {
	if reader == nil {
		return nil, errors.New("homepage query facade requires reader")
	}
	return &QueryFacade{reader: reader, followers: followers}, nil
}

func (f *QueryFacade) Get(
	ctx context.Context,
	rawID string,
	viewerPersonaID string,
	includeOffline bool,
) (View, error) {
	snapshot, found, err := f.reader.FindExact(ctx, homepageports.ExactLookup{
		ID:          strings.TrimSpace(rawID),
		LookupAlias: homepagemodel.NormalizeLookupAlias(rawID),
	})
	if err != nil {
		return View{}, unavailable(err)
	}
	if !found {
		return View{}, generated.AppErrorFromHomepageNotFound("homepage not found")
	}
	if snapshot.Status == homepagemodel.StatusOffline && !includeOffline {
		return View{}, generated.AppErrorFromHomepageOffline("homepage offline")
	}
	view := ViewFromSnapshot(snapshot)
	if f.followers != nil {
		followerView, followerErr := f.followers.ResolveFollowerView(ctx, snapshot.ID, viewerPersonaID)
		if followerErr != nil {
			return View{}, unavailable(followerErr)
		}
		view.FollowerCount = followerView.Count
		view.ViewerFollows = followerView.ViewerFollows
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
	query homepageports.SearchQuery,
) (SearchSlice, error) {
	page, err := f.reader.Search(ctx, query)
	if err != nil {
		return SearchSlice{}, unavailable(err)
	}
	result := SearchSlice{NextCursor: page.NextCursor, Items: []SearchItemView{}}
	for _, snapshot := range page.Items {
		result.Items = append(result.Items, SearchItemView{
			HomepageID:        snapshot.ID,
			CanonicalEntityID: snapshot.CanonicalEntityID,
			Title:             snapshot.Title,
			Subtitle:          snapshot.Subtitle,
			HomepageType:      snapshot.HomepageType,
			CoverURL:          snapshot.CoverURL,
			City:              snapshot.City,
			Address:           snapshot.Address,
			Status:            string(snapshot.Status),
			AverageRating:     cloneFloat(snapshot.AverageRating),
			RatingCount:       snapshot.RatingCount,
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
		views = append(views, ViewFromSnapshot(snapshot))
	}
	return views, page.NextCursor, nil
}

func (f *QueryFacade) Count(ctx context.Context) (int64, error) {
	count, err := f.reader.Count(ctx)
	if err != nil {
		return 0, unavailable(err)
	}
	return count, nil
}
