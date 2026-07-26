package circlegroup

import (
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
)

// SearchEligible keeps the shared public index free of private or archived
// CircleGroups. Member-scoped private group search remains on the named reader.
func CircleGroupSearchEligible(group groupmodel.CircleGroup) bool {
	return group.Status == groupmodel.CircleGroupStatusActive &&
		group.Visibility == groupmodel.CircleGroupVisibilityPublic &&
		strings.TrimSpace(group.ID) != "" &&
		strings.TrimSpace(group.CircleID) != ""
}

// ProjectToSearchDocument is the only CircleGroup -> search.Document mapping
// used by both write-time projection and full backfill.
func ProjectCircleGroupToSearchDocument(
	group groupmodel.CircleGroup,
) rtsearch.Document {
	return rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeCircleGroup,
		ObjectID:     group.ID,
		Title:        group.Name,
		Summary:      group.Description,
		SourceDomain: "circle",
		ContentType:  string(group.GroupType),
		Visibility:   string(group.Visibility),
		BadgeLabel:   "讨论",
		Freshness:    group.UpdatedAt.UTC(),
		Fields: map[string]string{
			"groupId":       group.ID,
			"circleId":      group.CircleID,
			"parentGroupId": group.ParentGroupID,
			"groupType":     string(group.GroupType),
			"nodeType":      string(group.NodeType),
		},
	}
}
