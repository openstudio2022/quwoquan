package skill

import (
	"sort"
	"strings"

	rctx "quwoquan_service/runtime/context"
)

// Router matches the current page context to applicable skills.
type Router struct {
	skills []Skill
}

func NewRouter() *Router {
	return &Router{}
}

func (r *Router) Register(skills ...Skill) {
	r.skills = append(r.skills, skills...)
}

func (r *Router) RegisteredSkills() []Skill { return r.skills }

// Match returns skills applicable to the given page context, sorted by priority.
func (r *Router) Match(pageCtx *rctx.PageContextSnapshot) []Skill {
	if pageCtx == nil {
		return nil
	}

	var matched []Skill
	for _, s := range r.skills {
		if matchesPage(s.Manifest(), pageCtx) {
			matched = append(matched, s)
		}
	}

	sort.Slice(matched, func(i, j int) bool {
		return matched[i].Manifest().Priority > matched[j].Manifest().Priority
	})

	return matched
}

func matchesPage(m SkillManifest, pageCtx *rctx.PageContextSnapshot) bool {
	for _, pm := range m.ApplicablePages {
		if pm.PageType != string(pageCtx.PageType) {
			continue
		}

		if len(pm.ContentTypes) > 0 && pageCtx.Objects.Post != nil {
			ct := pageCtx.Objects.Post.ContentType
			if !containsStr(pm.ContentTypes, ct) {
				continue
			}
		}

		if len(pm.TagMatch) > 0 {
			tags := extractPageTags(pageCtx)
			if !anyTagMatch(pm.TagMatch, tags) {
				continue
			}
		}

		return true
	}
	return false
}

func extractPageTags(pageCtx *rctx.PageContextSnapshot) []string {
	if pageCtx.Objects.Post != nil {
		return pageCtx.Objects.Post.Tags
	}
	if pageCtx.Objects.Circle != nil {
		return pageCtx.Objects.Circle.Tags
	}
	return nil
}

func anyTagMatch(patterns, tags []string) bool {
	for _, p := range patterns {
		for _, t := range tags {
			if strings.EqualFold(p, t) {
				return true
			}
		}
	}
	return false
}

func containsStr(ss []string, s string) bool {
	for _, v := range ss {
		if v == s {
			return true
		}
	}
	return false
}
