package collection

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"slices"
	"time"

	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
)

// PostReader 必须调用 Post owner 的当前权限 reader；不可读与依赖失败严格区分。
type PostReader interface {
	ReadVisible(context.Context, string, string) (Member, bool, error)
}

// CoverReader 不签发 URL，仅验证封面资产能按合集可见性安全交付。
type CoverReader interface {
	CanUseCover(context.Context, string, string, domain.Visibility) (bool, error)
}
type Member struct {
	PostID      string `json:"postId"`
	ContentType string `json:"contentType"`
	Title       string `json:"title"`
}
type Page struct {
	CollectionID   string            `json:"collectionId"`
	OwnerPersonaID string            `json:"ownerPersonaId"`
	Name           string            `json:"name"`
	CoverAssetID   *string           `json:"coverAssetId"`
	Visibility     domain.Visibility `json:"visibility"`
	Version        int64             `json:"version"`
	Members        []Member          `json:"members"`
	VisibleCount   int               `json:"visibleCount"`
	NextCursor     *string           `json:"nextCursor"`
	CanManage      bool              `json:"canManage"`
}
type Result struct {
	CollectionID string        `json:"collectionId"`
	Version      int64         `json:"version"`
	Status       domain.Status `json:"status"`
}
type Service struct {
	store  domain.Store
	posts  PostReader
	covers CoverReader
	now    func() time.Time
}

func New(store domain.Store, posts PostReader, covers CoverReader, now func() time.Time) (*Service, error) {
	if store == nil || posts == nil || covers == nil || now == nil {
		return nil, domain.Unavailable
	}
	return &Service{store, posts, covers, now}, nil
}
func result(c domain.Collection) Result { return Result{c.ID, c.Version, c.Status} }
func (s *Service) Save(ctx context.Context, actor string, in domain.Save) (Result, error) {
	if actor == "" {
		return Result{}, domain.Unauthorized
	}
	if err := in.Validate(); err != nil {
		return Result{}, err
	}
	old, found, err := s.store.Find(ctx, in.ID)
	if err != nil {
		return Result{}, fmt.Errorf("%w: %v", domain.StorageRead, err)
	}
	if found && old.Owner != actor {
		return Result{}, domain.Unavailable
	}
	if found && old.Status == domain.Deleted {
		return Result{}, domain.Unavailable
	}
	// 只重放紧邻成功版本，后续任何写入后旧命令都不能复活。
	if found && old.Version == in.ExpectedVersion+1 && old.Same(in) {
		return result(old), nil
	}
	if (!found && in.ExpectedVersion != 0) || (found && old.Version != in.ExpectedVersion) {
		return Result{}, domain.Conflict
	}
	oldIDs := map[string]bool{}
	for _, id := range old.PostIDs {
		oldIDs[id] = true
	}
	for _, id := range in.PostIDs {
		// 既有失权成员允许保留或移除；新增成员必须当前可见且为三种作品之一。
		if oldIDs[id] {
			continue
		}
		member, visible, readErr := s.posts.ReadVisible(ctx, id, actor)
		if readErr != nil {
			return Result{}, fmt.Errorf("%w: %v", domain.StorageRead, readErr)
		}
		if !visible || member.PostID != id {
			return Result{}, domain.Unavailable
		}
		if member.ContentType != "video" && member.ContentType != "image" && member.ContentType != "article" {
			return Result{}, domain.Invalid
		}
	}
	if in.CoverAssetID != "" {
		allowed, coverErr := s.covers.CanUseCover(ctx, in.CoverAssetID, actor, in.Visibility)
		if coverErr != nil {
			return Result{}, fmt.Errorf("%w: %v", domain.StorageRead, coverErr)
		}
		if !allowed {
			return Result{}, domain.Unavailable
		}
	}
	next := domain.Collection{ID: in.ID, Owner: actor, Name: in.Name, CoverAssetID: in.CoverAssetID, Visibility: in.Visibility, PostIDs: slices.Clone(in.PostIDs), Version: in.ExpectedVersion + 1, Status: domain.Active, UpdatedAt: s.now().UTC()}
	ok, err := s.store.CompareAndSwap(ctx, next, in.ExpectedVersion)
	if err != nil {
		return Result{}, fmt.Errorf("%w: %v", domain.StorageWrite, err)
	}
	if !ok {
		return Result{}, domain.Conflict
	}
	return result(next), nil
}
func (s *Service) Delete(ctx context.Context, actor, id string, expected int64) (Result, error) {
	if actor == "" {
		return Result{}, domain.Unauthorized
	}
	if id == "" || expected < 1 {
		return Result{}, domain.Invalid
	}
	old, found, err := s.store.Find(ctx, id)
	if err != nil {
		return Result{}, fmt.Errorf("%w: %v", domain.StorageRead, err)
	}
	if !found || old.Owner != actor {
		return Result{}, domain.Unavailable
	}
	if old.Status == domain.Deleted && old.Version == expected+1 {
		return result(old), nil
	}
	if old.Status != domain.Active || old.Version != expected {
		return Result{}, domain.Conflict
	}
	old.Status = domain.Deleted
	old.Version++
	old.UpdatedAt = s.now().UTC()
	ok, err := s.store.CompareAndSwap(ctx, old, expected)
	if err != nil {
		return Result{}, fmt.Errorf("%w: %v", domain.StorageWrite, err)
	}
	if !ok {
		return Result{}, domain.Conflict
	}
	return result(old), nil
}

type ManagedMember struct {
	PostID   string  `json:"postId"`
	Readable bool    `json:"readable"`
	Title    *string `json:"title"`
}
type ManagementView struct {
	CollectionID string            `json:"collectionId"`
	Name         string            `json:"name"`
	CoverAssetID *string           `json:"coverAssetId"`
	Visibility   domain.Visibility `json:"visibility"`
	Version      int64             `json:"version"`
	Members      []ManagedMember   `json:"members"`
}

// GetManagement 输出 owner 已拥有的编排引用，但不突破成员 Post 内容权限。
func (s *Service) GetManagement(ctx context.Context, actor, id string) (ManagementView, error) {
	if actor == "" {
		return ManagementView{}, domain.Unauthorized
	}
	c, found, err := s.store.Find(ctx, id)
	if err != nil {
		return ManagementView{}, domain.StorageRead
	}
	if !found || c.Owner != actor || c.Status != domain.Active {
		return ManagementView{}, domain.Unavailable
	}
	view := ManagementView{CollectionID: c.ID, Name: c.Name, Visibility: c.Visibility, Version: c.Version, Members: []ManagedMember{}}
	if c.CoverAssetID != "" {
		cover := c.CoverAssetID
		view.CoverAssetID = &cover
	}
	for _, id := range c.PostIDs {
		m, visible, e := s.posts.ReadVisible(ctx, id, actor)
		if e != nil {
			return ManagementView{}, domain.StorageRead
		}
		row := ManagedMember{PostID: id, Readable: visible}
		if visible {
			if m.PostID != id {
				return ManagementView{}, domain.StorageRead
			}
			title := m.Title
			row.Title = &title
		}
		view.Members = append(view.Members, row)
	}
	return view, nil
}

// cursor 只携带已展示末项的摘要，不暴露受限成员数量或编排下标。
type cursor struct {
	Collection string `json:"c"`
	Viewer     string `json:"u"`
	Version    int64  `json:"v"`
	Last       string `json:"l"`
}

func viewerKey(viewer string) string { return fmt.Sprintf("%x", sha256.Sum256([]byte(viewer))) }
func (s *Service) Get(ctx context.Context, viewer, id, after string, limit int) (Page, error) {
	if id == "" || limit < 1 || limit > 100 {
		return Page{}, domain.Invalid
	}
	c, found, err := s.store.Find(ctx, id)
	if err != nil {
		return Page{}, fmt.Errorf("%w: %v", domain.StorageRead, err)
	}
	if !found || c.Status != domain.Active || (c.Visibility != domain.Public && c.Owner != viewer) {
		return Page{}, domain.Unavailable
	}
	start := 0
	if after != "" {
		raw, e := base64.RawURLEncoding.DecodeString(after)
		if e != nil {
			return Page{}, domain.Invalid
		}
		var cur cursor
		if json.Unmarshal(raw, &cur) != nil || cur.Collection != id || cur.Viewer != viewerKey(viewer) || cur.Last == "" {
			return Page{}, domain.Invalid
		}
		if cur.Version != c.Version {
			return Page{}, domain.Conflict
		}
		start = -1
		for i, postID := range c.PostIDs {
			if viewerKey(postID) == cur.Last {
				start = i + 1
				break
			}
		}
		if start < 0 {
			return Page{}, domain.Invalid
		}
	}
	p := Page{CollectionID: c.ID, OwnerPersonaID: c.Owner, Name: c.Name, Visibility: c.Visibility, Version: c.Version, Members: []Member{}, CanManage: viewer != "" && c.Owner == viewer}
	if c.CoverAssetID != "" {
		allowed, e := s.covers.CanUseCover(ctx, c.CoverAssetID, viewer, c.Visibility)
		if e != nil {
			return Page{}, fmt.Errorf("%w: %v", domain.StorageRead, e)
		}
		if allowed {
			cover := c.CoverAssetID
			p.CoverAssetID = &cover
		}
	}
	nextOffset := -1
	for i, id := range c.PostIDs {
		m, visible, e := s.posts.ReadVisible(ctx, id, viewer)
		if e != nil {
			return Page{}, fmt.Errorf("%w: %v", domain.StorageRead, e)
		}
		if !visible {
			continue
		}
		if m.PostID != id {
			return Page{}, domain.StorageRead
		}
		p.VisibleCount++
		if i < start {
			continue
		}
		if len(p.Members) < limit {
			p.Members = append(p.Members, m)
		} else if nextOffset < 0 {
			nextOffset = i
		}
	}
	if nextOffset >= 0 {
		raw, _ := json.Marshal(cursor{c.ID, viewerKey(viewer), c.Version, viewerKey(p.Members[len(p.Members)-1].PostID)})
		next := base64.RawURLEncoding.EncodeToString(raw)
		p.NextCursor = &next
	}
	return p, nil
}
