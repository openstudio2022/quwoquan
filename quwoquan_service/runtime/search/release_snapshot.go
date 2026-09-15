package search

import (
	"fmt"
	"slices"
	"sort"
	"strings"
)

// 所有字段来自_shared/types.yaml；不解析旧协议或给缺字段补默认值。
type ReleaseCandidateObjectIdentity struct {
	Release       ReleaseCandidateBinding `json:"release" bson:"release"`
	ObjectType    string                  `json:"objectType" bson:"objectType"`
	ObjectID      string                  `json:"objectId" bson:"objectId"`
	SourceVersion int64                   `json:"sourceVersion" bson:"sourceVersion"`
	SourceDigest  string                  `json:"sourceDigest" bson:"sourceDigest"`
}
type ReleaseLocation struct {
	Latitude  float64 `json:"latitude" bson:"latitude"`
	Longitude float64 `json:"longitude" bson:"longitude"`
}
type ReleaseHomepagePublicSnapshot struct {
	Identity             ReleaseCandidateObjectIdentity `json:"identity" bson:"identity"`
	EntityRef            string                         `json:"entityRef" bson:"entityRef"`
	CanonicalEntityID    string                         `json:"canonicalEntityId" bson:"canonicalEntityId"`
	Title                string                         `json:"title" bson:"title"`
	HomepageType         string                         `json:"homepageType" bson:"homepageType"`
	IntroductionMarkdown string                         `json:"introductionMarkdown" bson:"introductionMarkdown"`
	City                 *string                        `json:"city" bson:"city"`
	Location             *ReleaseLocation               `json:"location" bson:"location"`
	CoverURL             *string                        `json:"coverUrl" bson:"coverUrl"`
	TagRefs              []string                       `json:"tagRefs" bson:"tagRefs"`
	DeepLink             string                         `json:"deepLink" bson:"deepLink"`
	UpdatedAt            string                         `json:"updatedAt" bson:"updatedAt"`
	DocumentDigest       string                         `json:"documentDigest" bson:"documentDigest"`
}
type ReleasePostPublicSnapshot struct {
	Identity          ReleaseCandidateObjectIdentity `json:"identity" bson:"identity"`
	PostRef           string                         `json:"postRef" bson:"postRef"`
	AuthorID          string                         `json:"authorId" bson:"authorId"`
	AuthorDisplayName string                         `json:"authorDisplayName" bson:"authorDisplayName"`
	AuthorAvatarURL   *string                        `json:"authorAvatarUrl" bson:"authorAvatarUrl"`
	ContentType       string                         `json:"contentType" bson:"contentType"`
	ContentIdentity   string                         `json:"contentIdentity" bson:"contentIdentity"`
	Status            string                         `json:"status" bson:"status"`
	Visibility        string                         `json:"visibility" bson:"visibility"`
	ModerationStatus  string                         `json:"moderationStatus" bson:"moderationStatus"`
	Title             string                         `json:"title" bson:"title"`
	Body              string                         `json:"body" bson:"body"`
	Summary           string                         `json:"summary" bson:"summary"`
	TagRefs           []string                       `json:"tagRefs" bson:"tagRefs"`
	EntityRefs        []string                       `json:"entityRefs" bson:"entityRefs"`
	PrimaryHomepage   *ReleaseHomepagePublicSnapshot `json:"primaryHomepage" bson:"primaryHomepage"`
	MediaAssetIDs     []string                       `json:"mediaAssetIds" bson:"mediaAssetIds"`
	MediaURLs         []string                       `json:"mediaUrls" bson:"mediaUrls"`
	CoverURL          *string                        `json:"coverUrl" bson:"coverUrl"`
	ThumbnailURL      *string                        `json:"thumbnailUrl" bson:"thumbnailUrl"`
	VideoURL          *string                        `json:"videoUrl" bson:"videoUrl"`
	DurationMs        int64                          `json:"durationMs" bson:"durationMs"`
	Width             int                            `json:"width" bson:"width"`
	Height            int                            `json:"height" bson:"height"`
	ContentVertical   *string                        `json:"contentVertical" bson:"contentVertical"`
	PublishedAt       string                         `json:"publishedAt" bson:"publishedAt"`
	UpdatedAt         string                         `json:"updatedAt" bson:"updatedAt"`
	DeepLink          string                         `json:"deepLink" bson:"deepLink"`
	DocumentDigest    string                         `json:"documentDigest" bson:"documentDigest"`
}
type ReleasePostCandidateSnapshot struct {
	Release             ReleaseCandidateBinding     `json:"release" bson:"release"`
	SourceClosureDigest string                      `json:"sourceClosureDigest" bson:"sourceClosureDigest"`
	MediaClosureDigest  string                      `json:"mediaClosureDigest" bson:"mediaClosureDigest"`
	ObjectSetDigest     string                      `json:"objectSetDigest" bson:"objectSetDigest"`
	SnapshotDigest      string                      `json:"snapshotDigest" bson:"snapshotDigest"`
	Posts               []ReleasePostPublicSnapshot `json:"posts" bson:"posts"`
}
type ReleaseHomepageCandidateSnapshot struct {
	Release                ReleaseCandidateBinding         `json:"release" bson:"release"`
	SourceClosureDigest    string                          `json:"sourceClosureDigest" bson:"sourceClosureDigest"`
	EntityRefMappingDigest string                          `json:"entityRefMappingDigest" bson:"entityRefMappingDigest"`
	ObjectSetDigest        string                          `json:"objectSetDigest" bson:"objectSetDigest"`
	SnapshotDigest         string                          `json:"snapshotDigest" bson:"snapshotDigest"`
	Homepages              []ReleaseHomepagePublicSnapshot `json:"homepages" bson:"homepages"`
}
type SearchReleaseCandidateSnapshot struct {
	Kind     string                            `json:"kind" bson:"kind"`
	Creator  *CreatorSearchCandidateSnapshot   `json:"creator" bson:"creator"`
	Post     *ReleasePostCandidateSnapshot     `json:"post" bson:"post"`
	Homepage *ReleaseHomepageCandidateSnapshot `json:"homepage" bson:"homepage"`
}

func (s SearchReleaseCandidateSnapshot) Release() ReleaseCandidateBinding {
	switch s.Kind {
	case "creator":
		if s.Creator != nil {
			return s.Creator.Release
		}
	case "post":
		if s.Post != nil {
			return s.Post.Release
		}
	case "homepage":
		if s.Homepage != nil {
			return s.Homepage.Release
		}
	}
	return ReleaseCandidateBinding{}
}
func (s SearchReleaseCandidateSnapshot) SnapshotDigest() string {
	switch s.Kind {
	case "creator":
		if s.Creator != nil {
			return s.Creator.SnapshotDigest
		}
	case "post":
		if s.Post != nil {
			return s.Post.SnapshotDigest
		}
	case "homepage":
		if s.Homepage != nil {
			return s.Homepage.SnapshotDigest
		}
	}
	return ""
}
func (s SearchReleaseCandidateSnapshot) ObjectSetDigest() string {
	switch s.Kind {
	case "creator":
		if s.Creator != nil {
			return s.Creator.ObjectSetDigest
		}
	case "post":
		if s.Post != nil {
			return s.Post.ObjectSetDigest
		}
	case "homepage":
		if s.Homepage != nil {
			return s.Homepage.ObjectSetDigest
		}
	}
	return ""
}
func (s SearchReleaseCandidateSnapshot) SourceClosureDigest() string {
	switch s.Kind {
	case "creator":
		if s.Creator != nil {
			return s.Creator.SourceClosureDigest
		}
	case "post":
		if s.Post != nil {
			return s.Post.SourceClosureDigest
		}
	case "homepage":
		if s.Homepage != nil {
			return s.Homepage.SourceClosureDigest
		}
	}
	return ""
}
func (s SearchReleaseCandidateSnapshot) Identities() []ReleaseCandidateObjectIdentity {
	out := []ReleaseCandidateObjectIdentity{}
	switch s.Kind {
	case "creator":
		if s.Creator != nil {
			for _, p := range s.Creator.Profiles {
				out = append(out, ReleaseCandidateObjectIdentity{s.Creator.Release, p.ObjectType, p.ObjectID, p.SourceVersion, p.SourceDigest})
			}
		}
	case "post":
		if s.Post != nil {
			for _, p := range s.Post.Posts {
				out = append(out, p.Identity)
			}
		}
	case "homepage":
		if s.Homepage != nil {
			for _, p := range s.Homepage.Homepages {
				out = append(out, p.Identity)
			}
		}
	}
	return out
}
func (s SearchReleaseCandidateSnapshot) Validate() error {
	count := 0
	for _, on := range []bool{s.Creator != nil, s.Post != nil, s.Homepage != nil} {
		if on {
			count++
		}
	}
	if count != 1 {
		return fmt.Errorf("exactly one typed source required")
	}
	switch s.Kind {
	case "creator":
		if s.Creator == nil {
			return ErrCreatorSourceInvalid
		}
		return s.Creator.Validate()
	case "post":
		if s.Post == nil {
			return ErrCreatorSourceInvalid
		}
		return s.Post.Validate()
	case "homepage":
		if s.Homepage == nil {
			return ErrCreatorSourceInvalid
		}
		return s.Homepage.Validate()
	default:
		return ErrCreatorSourceInvalid
	}
}
func validateSourceIdentity(i ReleaseCandidateObjectIdentity, release ReleaseCandidateBinding, kind string) error {
	if i.Release != release || release.Validate() != nil || i.ObjectType != kind || strings.TrimSpace(i.ObjectID) == "" || i.SourceVersion < 1 || !creatorDigestPattern.MatchString(i.SourceDigest) {
		return ErrCreatorSourceInvalid
	}
	return nil
}
func (p ReleaseHomepagePublicSnapshot) Validate(release ReleaseCandidateBinding) error {
	if validateSourceIdentity(p.Identity, release, "entity.homepage") != nil || strings.TrimSpace(p.EntityRef) == "" || strings.TrimSpace(p.CanonicalEntityID) == "" || strings.TrimSpace(p.Title) == "" || !slices.Contains([]string{"vehicle", "hotel", "restaurant", "sight", "university", "school", "travel_photo", "museum", "heritage_site", "ancient_town", "religious_site", "check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park", "transport_hub", "city", "route", "photo_spot", "gear"}, p.HomepageType) || p.TagRefs == nil || p.DeepLink == "" || !validCreatorTime(p.UpdatedAt) {
		return ErrCreatorSourceInvalid
	}
	d, _ := CreatorCanonicalDigest(p, "documentDigest")
	if d != p.DocumentDigest {
		return ErrCreatorSourceInvalid
	}
	return nil
}
func (p ReleasePostPublicSnapshot) Validate(release ReleaseCandidateBinding) error {
	if validateSourceIdentity(p.Identity, release, "content.post") != nil || p.PostRef == "" || p.AuthorID == "" || p.AuthorDisplayName == "" || p.Status != "published" || p.Visibility != "public" || p.ModerationStatus != "approved" || p.TagRefs == nil || p.EntityRefs == nil || p.MediaAssetIDs == nil || p.MediaURLs == nil || p.DurationMs < 0 || p.Width < 0 || p.Height < 0 || p.DeepLink == "" || !validCreatorTime(p.PublishedAt) || !validCreatorTime(p.UpdatedAt) {
		return ErrCreatorSourceInvalid
	}
	if p.ContentType != "article" && p.ContentType != "image" && p.ContentType != "video" && p.ContentType != "micro" {
		return ErrCreatorSourceInvalid
	}
	if p.ContentIdentity != "work" && p.ContentIdentity != "moment" {
		return ErrCreatorSourceInvalid
	}
	if p.PrimaryHomepage != nil && p.PrimaryHomepage.Validate(release) != nil {
		return ErrCreatorSourceInvalid
	}
	d, _ := CreatorCanonicalDigest(p, "documentDigest")
	if d != p.DocumentDigest {
		return ErrCreatorSourceInvalid
	}
	return nil
}
func identitySetDigest(ids []ReleaseCandidateObjectIdentity) string {
	rows := []map[string]string{}
	for _, i := range ids {
		rows = append(rows, map[string]string{"objectType": i.ObjectType, "objectId": i.ObjectID})
	}
	d, _ := CreatorCanonicalDigest(rows, "")
	return d
}
func (s ReleasePostCandidateSnapshot) Validate() error {
	if s.Release.Validate() != nil || s.Posts == nil || len(s.Posts) > 1000 || !creatorDigestPattern.MatchString(s.SourceClosureDigest) || !creatorDigestPattern.MatchString(s.MediaClosureDigest) {
		return ErrCreatorSourceInvalid
	}
	ids := []ReleaseCandidateObjectIdentity{}
	last := ""
	for _, p := range s.Posts {
		if p.Validate(s.Release) != nil || p.Identity.ObjectID <= last {
			return ErrCreatorSourceInvalid
		}
		last = p.Identity.ObjectID
		ids = append(ids, p.Identity)
	}
	d, _ := CreatorCanonicalDigest(s, "snapshotDigest")
	if d != s.SnapshotDigest || identitySetDigest(ids) != s.ObjectSetDigest {
		return ErrCreatorSourceInvalid
	}
	return nil
}
func (s ReleaseHomepageCandidateSnapshot) Validate() error {
	if s.Release.Validate() != nil || s.Homepages == nil || len(s.Homepages) > 1000 || !creatorDigestPattern.MatchString(s.SourceClosureDigest) || !creatorDigestPattern.MatchString(s.EntityRefMappingDigest) {
		return ErrCreatorSourceInvalid
	}
	ids := []ReleaseCandidateObjectIdentity{}
	last := ""
	for _, p := range s.Homepages {
		if p.Validate(s.Release) != nil || p.Identity.ObjectID <= last {
			return ErrCreatorSourceInvalid
		}
		last = p.Identity.ObjectID
		ids = append(ids, p.Identity)
	}
	d, _ := CreatorCanonicalDigest(s, "snapshotDigest")
	if d != s.SnapshotDigest || identitySetDigest(ids) != s.ObjectSetDigest {
		return ErrCreatorSourceInvalid
	}
	return nil
}
func (s *ReleasePostCandidateSnapshot) Seal() error {
	sort.Slice(s.Posts, func(i, j int) bool { return s.Posts[i].Identity.ObjectID < s.Posts[j].Identity.ObjectID })
	ids := []ReleaseCandidateObjectIdentity{}
	for i := range s.Posts {
		d, e := CreatorCanonicalDigest(s.Posts[i], "documentDigest")
		if e != nil {
			return e
		}
		s.Posts[i].DocumentDigest = d
		ids = append(ids, s.Posts[i].Identity)
	}
	s.ObjectSetDigest = identitySetDigest(ids)
	d, e := CreatorCanonicalDigest(s, "snapshotDigest")
	s.SnapshotDigest = d
	return e
}
func (s *ReleaseHomepageCandidateSnapshot) Seal() error {
	sort.Slice(s.Homepages, func(i, j int) bool { return s.Homepages[i].Identity.ObjectID < s.Homepages[j].Identity.ObjectID })
	ids := []ReleaseCandidateObjectIdentity{}
	for i := range s.Homepages {
		d, e := CreatorCanonicalDigest(s.Homepages[i], "documentDigest")
		if e != nil {
			return e
		}
		s.Homepages[i].DocumentDigest = d
		ids = append(ids, s.Homepages[i].Identity)
	}
	s.ObjectSetDigest = identitySetDigest(ids)
	d, e := CreatorCanonicalDigest(s, "snapshotDigest")
	s.SnapshotDigest = d
	return e
}
