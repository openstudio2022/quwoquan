package impact

import "testing"

func TestBuildStatementRequiresNamedActorAndRoutableObject(t *testing.T) {
	userTarget := &Target{ObjectType: "user", ObjectID: "user_1", ObjectKind: "person", RouteID: "profile"}
	statement, ok := BuildStatement(StatementEvidence{
		HelpType:              HelpCommunity,
		Action:                "join_circle",
		IntersectionDimension: "relationship",
		Source:                "circle_members",
		Count:                 12,
		ImpactID:              "impact_1",
		EvidenceSnapshotID:    "snapshot_1",
		RepresentativeActor: RepresentativeActor{
			ActorID:       "user_1",
			DisplayName:   "契约摄影社主理人",
			RelationLabel: "圈子主理人",
			Target:        userTarget,
		},
		ObjectName:   "契约摄影社",
		ObjectTarget: Target{ObjectType: "circle", ObjectID: "circle_1", ObjectKind: "circle", RouteID: "circleDetail"},
	})
	if !ok {
		t.Fatal("expected complete evidence to build statement")
	}
	if statement.PrimaryText != "契约摄影社主理人等12人加入了契约摄影社" {
		t.Fatalf("primaryText = %q", statement.PrimaryText)
	}
	joined := ""
	hasObject := false
	for _, span := range statement.PrimarySpans {
		joined += span.Text
		if span.Role == "object" && span.Target != nil && span.Target.ObjectType == "circle" {
			hasObject = true
		}
	}
	if joined != statement.PrimaryText || !hasObject {
		t.Fatalf("invalid spans: %+v", statement.PrimarySpans)
	}
	if statement.RepresentativeActor == nil || statement.RepresentativeActor.Target == nil || statement.RepresentativeActor.Target.ObjectType != "user" {
		t.Fatalf("invalid representative actor: %+v", statement.RepresentativeActor)
	}
}

func TestBuildStatementFailsClosedForSyntheticOrIncompleteEvidence(t *testing.T) {
	base := StatementEvidence{
		HelpType:           HelpCommunity,
		Action:             "join_circle",
		Source:             "circle_members",
		Count:              12,
		ImpactID:           "impact_1",
		EvidenceSnapshotID: "snapshot_1",
		RepresentativeActor: RepresentativeActor{
			ActorID:       "user_1",
			DisplayName:   "一位用户",
			RelationLabel: "圈子主理人",
			Target:        &Target{ObjectType: "user", ObjectID: "user_1", RouteID: "profile"},
		},
		ObjectName:   "契约摄影社",
		ObjectTarget: Target{ObjectType: "circle", ObjectID: "circle_1", RouteID: "circleDetail"},
	}
	if _, ok := BuildStatement(base); ok {
		t.Fatal("synthetic actor must fail closed")
	}
	base.RepresentativeActor.DisplayName = "契约摄影社主理人"
	base.EvidenceSnapshotID = ""
	if _, ok := BuildStatement(base); ok {
		t.Fatal("missing evidence snapshot must fail closed")
	}
}
