package bootstrap

import (
	"net/http"
	"strings"

	behaviorhttp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	filehttp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/adapters/inbound/http"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	grouphttp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/http"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupmembershiphttp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/adapters/inbound/http"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	membershiphttp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/adapters/inbound/http"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	placementhttp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/http"
	placementapp "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
)

type circleObjectRoutes struct {
	fallback         http.Handler
	behaviors        *behaviorhttp.Handler
	files            *filehttp.Handler
	groups           *grouphttp.Handler
	groupMemberships *groupmembershiphttp.Handler
	memberships      *membershiphttp.Handler
	placements       *placementhttp.Handler
}

func newCircleObjectRoutes(
	fallback http.Handler,
	fileCommands *fileapp.CommandFacade,
	fileQueries *fileapp.QueryFacade,
	behaviorFacts *behaviorapp.Writer,
	groupCommands *groupapp.CommandFacade,
	groupQueries *groupapp.QueryFacade,
	groupMembershipCommands *groupmembershipapp.CommandFacade,
	groupMembershipQueries *groupmembershipapp.QueryFacade,
	membershipCommands *membershipapp.CommandFacade,
	membershipQueries *membershipapp.QueryFacade,
	placementCommands *placementapp.CommandFacade,
) http.Handler {
	if fallback == nil {
		panic("Circle object route composition requires Circle fallback")
	}
	return &circleObjectRoutes{
		fallback:         fallback,
		behaviors:        behaviorhttp.NewHandler(behaviorFacts),
		files:            filehttp.NewHandler(fileCommands, fileQueries),
		groups:           grouphttp.NewHandler(groupCommands, groupQueries),
		groupMemberships: groupmembershiphttp.NewHandler(groupMembershipCommands, groupMembershipQueries),
		memberships:      membershiphttp.NewHandler(membershipCommands, membershipQueries),
		placements:       placementhttp.NewHandler(placementCommands),
	}
}

func (routes *circleObjectRoutes) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	if request.URL.Path == "/circles/behaviors" {
		routes.behaviors.ServeHTTP(writer, request)
		return
	}
	if strings.HasPrefix(request.URL.Path, "/personas/") {
		routes.memberships.ServePersonaCircles(writer, request)
		return
	}
	if !strings.HasPrefix(request.URL.Path, "/circles/") {
		routes.fallback.ServeHTTP(writer, request)
		return
	}
	parts := strings.Split(strings.Trim(strings.TrimPrefix(request.URL.Path, "/circles/"), "/"), "/")
	if len(parts) < 2 || strings.TrimSpace(parts[0]) == "" {
		routes.fallback.ServeHTTP(writer, request)
		return
	}
	circleID, subResource, rest := parts[0], parts[1], parts[2:]
	switch subResource {
	case "memberships":
		routes.memberships.ServeCircleRoute(writer, request, circleID, rest)
	case "groups":
		if len(rest) >= 2 && rest[1] == "memberships" {
			routes.groupMemberships.ServeCircleGroupRoute(writer, request, circleID, rest[0], rest[2:])
			return
		}
		routes.groups.ServeCircleRoute(writer, request, circleID, rest)
	case "files":
		routes.files.ServeCircleRoute(writer, request, circleID, rest)
	case "post-placements":
		routes.placements.ServeCircleRoute(writer, request, circleID, rest)
	default:
		routes.fallback.ServeHTTP(writer, request)
	}
}
