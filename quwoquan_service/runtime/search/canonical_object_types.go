package search

import (
	"fmt"
	"strings"
)

// Canonical wire vocabulary for the unified search(request) filter.
//
// objectTypes on the public contract only accept the canonical object names
// below; contentTypes only accept article/image/video and narrow the
// content.post family. The recall Target vocabulary (article/photo/video/
// user/entity/circle/group/location) is an implementation detail derived
// here and must never appear on any external wire, GraphQL schema, App enum
// or assistant tool parameter.
//
// Single source of the bindings:
// quwoquan_service/contracts/metadata/_shared/search_objects.yaml
// (object_types + ai_targets.object_type/content_type).
const (
	CanonicalObjectContentPost    = "content.post"
	CanonicalObjectUserProfile    = "user.profile"
	CanonicalObjectEntityHomepage = "entity.homepage"
	CanonicalObjectCircle         = "circle.circle"
	CanonicalObjectCircleGroup    = "circle.group"
	CanonicalObjectLocationPlace  = "location.place"

	CanonicalContentArticle = "article"
	CanonicalContentImage   = "image"
	CanonicalContentVideo   = "video"
)

// CloudSearchableObjectTypes lists the canonical object vocabulary the unified
// cloud index can serve. chat.* stays local_only, tag is filter_only and
// web.document / integration.location_poi are owned by other providers.
var CloudSearchableObjectTypes = []string{
	CanonicalObjectCircle,
	CanonicalObjectCircleGroup,
	CanonicalObjectContentPost,
	CanonicalObjectEntityHomepage,
	CanonicalObjectLocationPlace,
	CanonicalObjectUserProfile,
}

var canonicalObjectTargets = map[string][]Target{
	CanonicalObjectContentPost:    {TargetArticle, TargetPhoto, TargetVideo},
	CanonicalObjectUserProfile:    {TargetUser},
	CanonicalObjectEntityHomepage: {TargetEntity},
	CanonicalObjectCircle:         {TargetCircle},
	CanonicalObjectCircleGroup:    {TargetGroup},
	CanonicalObjectLocationPlace:  {TargetLocation},
}

var canonicalContentTargets = map[string]Target{
	CanonicalContentArticle: TargetArticle,
	CanonicalContentImage:   TargetPhoto,
	CanonicalContentVideo:   TargetVideo,
}

func isContentTarget(target Target) bool {
	return target == TargetArticle || target == TargetPhoto || target == TargetVideo
}

// TargetsForCanonicalFilter maps the canonical objectTypes/contentTypes wire
// filter onto recall targets. Empty objectTypes start from defaults; unknown
// vocabulary fails closed instead of silently widening to the default scope.
// contentTypes narrow only the content.post family and leave other requested
// object types untouched.
func TargetsForCanonicalFilter(objectTypes, contentTypes []string, defaults []Target) ([]Target, error) {
	targets := []Target{}
	seen := map[Target]bool{}
	add := func(values ...Target) {
		for _, value := range values {
			if !seen[value] {
				seen[value] = true
				targets = append(targets, value)
			}
		}
	}
	if len(objectTypes) == 0 {
		add(defaults...)
	} else {
		for _, raw := range objectTypes {
			key := strings.ToLower(strings.TrimSpace(raw))
			if key == "" {
				continue
			}
			mapped, known := canonicalObjectTargets[key]
			if !known {
				return nil, fmt.Errorf("unsupported search object type %q", raw)
			}
			add(mapped...)
		}
		if len(targets) == 0 {
			add(defaults...)
		}
	}
	if len(contentTypes) == 0 {
		return targets, nil
	}
	allowedContent := map[Target]bool{}
	for _, raw := range contentTypes {
		key := strings.ToLower(strings.TrimSpace(raw))
		if key == "" {
			continue
		}
		target, known := canonicalContentTargets[key]
		if !known {
			return nil, fmt.Errorf("unsupported search content type %q", raw)
		}
		allowedContent[target] = true
	}
	if len(allowedContent) == 0 {
		return targets, nil
	}
	filtered := make([]Target, 0, len(targets))
	for _, target := range targets {
		if isContentTarget(target) && !allowedContent[target] {
			continue
		}
		filtered = append(filtered, target)
	}
	return filtered, nil
}
