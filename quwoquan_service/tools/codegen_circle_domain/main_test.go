package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCircleModelCodegen_PreservesObjectBoundaries(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if _, err := os.Stat(metadataDir); err != nil {
		t.Fatalf("metadata dir is required: %v", err)
	}
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}
	out := t.TempDir()
	objects := map[string][]string{
		"Circle":              {"type Circle struct", "SubCategory", "Kind", "DisplaySubjectType", "FollowEnabled", "DefaultPublicGroupID", "LinkedHomepageID", "type CircleJoinPolicy", "CircleJoinPolicyInviteOnly", "[]CircleSectionConfig"},
		"CircleFile":          {"type CircleFile struct", "type CircleFileStatus", "type CircleFileType"},
		"CircleGroup":         {"type CircleGroup struct", "type CircleGroupStatus", "type OrganizationNodeType"},
		"CircleMembership":    {"type CircleMembership struct", "type CircleMemberRole", "type CircleMembershipState"},
		"CirclePostPlacement": {"type CirclePostPlacement struct", "OwnerPersonaID", "PinnedAt"},
	}
	paths := map[string]string{
		"Circle":              filepath.Join("circle", "contract", "model", "circle.go"),
		"CircleFile":          filepath.Join("circle_file", "contract", "model", "circle_file.go"),
		"CircleGroup":         filepath.Join("circle_group", "contract", "model", "circle_group.go"),
		"CircleMembership":    filepath.Join("circle_membership", "contract", "model", "circle_membership.go"),
		"CirclePostPlacement": filepath.Join("circle_post_placement", "contract", "model", "circle_post_placement.go"),
	}
	for object, needles := range objects {
		generator := contractcodegen.NewDomainGenerator(
			source,
			filepath.Join(out, contractcodegen.CamelToSnake(object)),
			contractcodegen.WithTypedEnums(),
			contractcodegen.WithSliceEntityRefs(),
			contractcodegen.WithSkipViewEntities(),
			contractcodegen.WithGoFieldIDSuffix(),
			contractcodegen.WithBusinessObjectEntitiesOnly(),
			contractcodegen.WithObjectFirstRoot(),
		)
		if err := generator.GenerateDomainModel(object); err != nil {
			t.Fatalf("GenerateDomainModel(%s): %v", object, err)
		}
		b, err := os.ReadFile(filepath.Join(out, paths[object]))
		if err != nil {
			t.Fatalf("read %s model: %v", object, err)
		}
		s := string(b)
		for _, needle := range needles {
			if !strings.Contains(s, needle) {
				t.Errorf("generated %s model missing %q", object, needle)
			}
		}
		if object == "Circle" && strings.Contains(s, "type CircleGroup struct") {
			t.Fatal("Circle aggregate must not absorb CircleGroup")
		}
		if object == "CircleMembership" && strings.Contains(s, "type CircleMember struct") {
			t.Fatal("CircleMembership aggregate must not restore retired CircleMember type")
		}
		if strings.Contains(s, "CommandReceipt struct") || strings.Contains(s, "Request struct") ||
			strings.Contains(s, "Outbox struct") || strings.Contains(s, "ProjectionCheckpoint struct") ||
			strings.Contains(s, "Inbox struct") {
			t.Fatalf("generated %s domain model contains infrastructure or transport entity", object)
		}
	}
}

func TestCircleObjectErrorPathsRequireObjectOwnership(t *testing.T) {
	t.Parallel()

	paths, err := circleObjectErrorPaths([]string{
		"circle/circle_management/circle_membership/errors.yaml",
		"circle/circle_management/circle/errors.yaml",
		"circle/circle_management/circle_group/errors.yaml",
	})
	if err != nil {
		t.Fatalf("circleObjectErrorPaths() error = %v", err)
	}
	want := []string{
		"circle/circle_management/circle/errors.yaml",
		"circle/circle_management/circle_group/errors.yaml",
		"circle/circle_management/circle_membership/errors.yaml",
	}
	if strings.Join(paths, "|") != strings.Join(want, "|") {
		t.Fatalf("circleObjectErrorPaths() = %v, want %v", paths, want)
	}

	invalid := [][]string{
		nil,
		{"circle/circle_management/errors.yaml"},
		{"circle/other/circle/errors.yaml"},
		{"circle/circle_management/circle/internal/errors.yaml"},
	}
	for _, input := range invalid {
		if _, err := circleObjectErrorPaths(input); err == nil {
			t.Fatalf("circleObjectErrorPaths(%v) unexpectedly succeeded", input)
		}
	}
}

func TestCircleErrorsCodegen_PreservesObjectBoundaries(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}
	out := t.TempDir()
	count, err := generateErrors(source, out, false)
	if err != nil {
		t.Fatalf("generateErrors() error = %v", err)
	}
	errorPaths, err := circleObjectErrorPaths(
		source.Paths("circle/circle_management/", "/errors.yaml"),
	)
	if err != nil {
		t.Fatalf("discover Circle error paths: %v", err)
	}
	if count != len(errorPaths) {
		t.Fatalf("generateErrors() count = %d, want %d", count, len(errorPaths))
	}
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		object := parts[2]
		generated, err := os.ReadFile(filepath.Join(out, object, "errors.go"))
		if err != nil {
			t.Fatalf("read generated %s errors: %v", object, err)
		}
		if !strings.Contains(string(generated), "from "+sourcePath+". DO NOT EDIT.") {
			t.Errorf("generated %s errors lost canonical source %s", object, sourcePath)
		}
	}
	if generated, err := os.ReadFile(filepath.Join(out, "circle", "errors.go")); err != nil {
		t.Fatalf("read generated circle errors: %v", err)
	} else if strings.Contains(string(generated), "ErrGroupNotFound") {
		t.Fatal("Circle errors must not absorb CircleGroup-specific errors")
	}
	if generated, err := os.ReadFile(filepath.Join(out, "circle_group", "errors.go")); err != nil {
		t.Fatalf("read generated CircleGroup errors: %v", err)
	} else if !strings.Contains(string(generated), "ErrGroupNotFound") {
		t.Fatal("CircleGroup errors must remain owned by CircleGroup")
	}
	if _, err := generateErrors(source, out, true); err != nil {
		t.Fatalf("generated Circle errors should be current: %v", err)
	}
	stalePath := filepath.Join(out, "circle_group", "errors.go")
	if err := os.WriteFile(stalePath, []byte("package generated\n"), 0o644); err != nil {
		t.Fatalf("write stale CircleGroup errors: %v", err)
	}
	if _, err := generateErrors(source, out, true); err == nil ||
		!strings.Contains(err.Error(), "generated errors are stale") {
		t.Fatalf("stale generated CircleGroup errors were not rejected: %v", err)
	}
}

func TestGatheringServiceClientCodegen_CoversGraphAndRejectsStaleOutput(
	t *testing.T,
) {
	metadataDir := contractsview.Build(t)
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile ContractGraph source: %v", err)
	}
	gatheringPlanObjects := 0
	for _, object := range source.Graph().Objects {
		if object.ID != "circle.gathering_plan" {
			continue
		}
		gatheringPlanObjects++
		if object.SourcePath != "circle/circle_management/gathering_plan/object.yaml" {
			t.Fatalf(
				"circle.gathering_plan source=%q, want canonical object.yaml",
				object.SourcePath,
			)
		}
	}
	if gatheringPlanObjects != 1 {
		t.Fatalf(
			"ContractGraph source has %d circle.gathering_plan objects, want 1",
			gatheringPlanObjects,
		)
	}
	plans, err := circleDomainGenerationPlans(source)
	if err != nil {
		t.Fatalf("derive Circle domain generation plans: %v", err)
	}
	planNames := make([]string, 0, len(plans))
	var gatheringPlan circleDomainGenerationPlan
	for _, plan := range plans {
		planNames = append(planNames, plan.Name)
		if !plan.GenerateModel {
			t.Fatalf("Circle domain plan %s must generate its declared model", plan.Name)
		}
		if plan.Name == "GatheringPlan" {
			gatheringPlan = plan
		}
	}
	if !containsString(planNames, "GatheringPlan") {
		t.Fatalf("Circle domain generation plans omit GatheringPlan: %v", planNames)
	}
	if containsString(planNames, "CircleSearchItemView") {
		t.Fatalf(
			"projection-only CircleSearchItemView must not produce an empty domain model: %v",
			planNames,
		)
	}
	if !gatheringPlan.GenerateEvents {
		t.Fatal("GatheringPlan events.yaml must produce an event packet")
	}
	modelOutputRoot := t.TempDir()
	gatheringPlanGenerator := contractcodegen.NewDomainGenerator(
		source,
		filepath.Join(modelOutputRoot, "gathering_plan"),
		contractcodegen.WithTypedEnums(),
		contractcodegen.WithSliceEntityRefs(),
		contractcodegen.WithSkipViewEntities(),
		contractcodegen.WithGoFieldIDSuffix(),
		contractcodegen.WithBusinessObjectEntitiesOnly(),
		contractcodegen.WithObjectFirstRoot(),
	)
	if err := gatheringPlanGenerator.GenerateDomainModel(gatheringPlan.Name); err != nil {
		t.Fatalf("generate GatheringPlan model from source plan: %v", err)
	}
	if err := gatheringPlanGenerator.GenerateDomainEvents(gatheringPlan.Name); err != nil {
		t.Fatalf("generate GatheringPlan events from source plan: %v", err)
	}
	generatedModel, err := os.ReadFile(filepath.Join(
		modelOutputRoot,
		"gathering_plan",
		"contract",
		"model",
		"gathering_plan.go",
	))
	if err != nil {
		t.Fatalf("read generated GatheringPlan model: %v", err)
	}
	if !strings.Contains(string(generatedModel), "type GatheringPlan struct") {
		t.Fatal("generated GatheringPlan model omitted its aggregate root")
	}
	generatedEvents, err := os.ReadFile(filepath.Join(
		modelOutputRoot,
		"gathering_plan",
		"contract",
		"event",
		"events.go",
	))
	if err != nil {
		t.Fatalf("read generated GatheringPlan events: %v", err)
	}
	if !strings.Contains(string(generatedEvents), "GatheringPlanCreated") {
		t.Fatal("generated GatheringPlan events omitted GatheringPlanCreated")
	}
	errorPaths, err := circleObjectErrorPaths(
		source.Paths("circle/circle_management/", "/errors.yaml"),
	)
	if err != nil {
		t.Fatalf("discover Circle error owners: %v", err)
	}
	gatheringPlanErrors := 0
	for _, sourcePath := range errorPaths {
		if sourcePath == "circle/circle_management/gathering_plan/errors.yaml" {
			gatheringPlanErrors++
		}
	}
	if gatheringPlanErrors != 1 {
		t.Fatalf(
			"Circle error source contains %d gathering_plan owners, want 1: %v",
			gatheringPlanErrors,
			errorPaths,
		)
	}
	expectedOperations := make([]string, 0)
	for _, operation := range source.Graph().Operations {
		if operation.ObjectID != gatheringObjectID {
			continue
		}
		if operation.SourcePath != gatheringOperationsPath {
			t.Fatalf(
				"Gathering operation %s source=%q, want %q",
				operation.ID,
				operation.SourcePath,
				gatheringOperationsPath,
			)
		}
		if strings.TrimSpace(operation.RequestEntity) == "" ||
			strings.TrimSpace(operation.ResponseEntity) == "" {
			t.Fatalf(
				"Gathering operation %s must retain typed request/response entities",
				operation.ID,
			)
		}
		expectedOperations = append(expectedOperations, operation.ID)
	}
	if len(expectedOperations) == 0 {
		t.Fatal("ContractGraph source has no circle.gathering operations")
	}
	outputRoot := t.TempDir()
	publicClientOutput := filepath.Join(
		outputRoot,
		"serviceclients",
		"circlegathering",
		"gathering_service_client.g.go",
	)
	privateAliasOutput := filepath.Join(
		outputRoot,
		"circle_management",
		"gathering",
		"contract",
		"client",
		"gathering_service_client.g.go",
	)
	pathsOutput := filepath.Join(outputRoot, "serviceclients", "circle_paths.g.go")

	count, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		false,
	)
	if err != nil {
		t.Fatalf("generate Gathering service client: %v", err)
	}
	if count != len(expectedOperations) {
		t.Fatalf(
			"generated operation count=%d, want source-derived %d",
			count,
			len(expectedOperations),
		)
	}
	client, err := os.ReadFile(publicClientOutput)
	if err != nil {
		t.Fatalf("read generated Gathering client: %v", err)
	}
	privateAlias, err := os.ReadFile(privateAliasOutput)
	if err != nil {
		t.Fatalf("read generated Gathering private alias: %v", err)
	}
	paths, err := os.ReadFile(pathsOutput)
	if err != nil {
		t.Fatalf("read generated Gathering paths: %v", err)
	}
	for _, needle := range []string{
		"type GatheringPublicDetailSlice struct",
		"type GatheringPrivateDetailSlice struct",
		"type GatheringBySourcePageSlice struct",
		"func EncodeCreateGatheringDraft(",
		"func EncodeListGatheringsBySource(",
		"func EncodeGetPublicGathering(",
		"func EncodeWatchGatheringAvailability(",
		"CanonicalRequestDigest",
	} {
		if !strings.Contains(string(client), needle) {
			t.Errorf("generated Gathering client missing %q", needle)
		}
	}
	for _, needle := range []string{
		`import shared "quwoquan_service/generated/serviceclients/circlegathering"`,
		"type GatheringIDQuery = shared.GatheringIDQuery",
		"func EncodeGetGathering(request GatheringIDQuery) (RequestPacket, error)",
	} {
		if !strings.Contains(string(privateAlias), needle) {
			t.Errorf("generated Gathering private alias missing %q", needle)
		}
	}
	if strings.Contains(
		string(client),
		"services/circle-service/",
	) || strings.Contains(
		string(privateAlias),
		"type GatheringIDQuery struct",
	) {
		t.Fatal("public client or private alias restored a cross-service/duplicate DTO truth")
	}
	for _, needle := range []string{
		"CircleGatheringCreateGatheringDraftOperationID",
		"CircleGatheringGetPublicGatheringPath",
		"CircleGatheringWatchGatheringAvailabilityPath",
		"CommercialStatus",
		"Idempotency",
	} {
		if !strings.Contains(string(paths), needle) {
			t.Errorf("generated Gathering paths missing %q", needle)
		}
	}
	for _, operationID := range expectedOperations {
		if !strings.Contains(string(paths), operationID) {
			t.Errorf(
				"generated Gathering paths missing source operation %q",
				operationID,
			)
		}
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		true,
	); err != nil {
		t.Fatalf("fresh Gathering generated outputs rejected: %v", err)
	}
	if err := os.WriteFile(pathsOutput, []byte("package serviceclients\n"), 0o644); err != nil {
		t.Fatalf("write stale Gathering paths: %v", err)
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		true,
	); err == nil || !strings.Contains(err.Error(), "generated output is stale") {
		t.Fatalf("stale Gathering generated output was not rejected: %v", err)
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		false,
	); err != nil {
		t.Fatalf("restore Gathering generated output: %v", err)
	}
	if err := os.WriteFile(
		publicClientOutput,
		[]byte("package circlegathering\n"),
		0o644,
	); err != nil {
		t.Fatalf("write stale public Gathering client: %v", err)
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		true,
	); err == nil || !strings.Contains(err.Error(), "generated output is stale") {
		t.Fatalf("stale public Gathering client was not rejected: %v", err)
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		false,
	); err != nil {
		t.Fatalf("restore public Gathering client: %v", err)
	}
	if err := os.WriteFile(
		privateAliasOutput,
		[]byte("package gatheringclient\n"),
		0o644,
	); err != nil {
		t.Fatalf("write stale private Gathering alias: %v", err)
	}
	if _, err := generateGatheringServiceClient(
		source,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		true,
	); err == nil || !strings.Contains(err.Error(), "generated output is stale") {
		t.Fatalf("stale private Gathering alias was not rejected: %v", err)
	}

	expectedPlanOperations := make([]string, 0)
	for _, operation := range source.Graph().Operations {
		if operation.ObjectID == gatheringPlanObjectID {
			if operation.SourcePath != gatheringPlanOperationsPath ||
				strings.TrimSpace(operation.RequestEntity) == "" ||
				strings.TrimSpace(operation.ResponseEntity) == "" {
				t.Fatalf(
					"GatheringPlan operation is not canonical/typed: %+v",
					operation,
				)
			}
			expectedPlanOperations = append(expectedPlanOperations, operation.ID)
		}
	}
	if len(expectedPlanOperations) == 0 {
		t.Fatal("ContractGraph source has no circle.gathering_plan operations")
	}
	planPublicClientOutput := filepath.Join(
		outputRoot,
		"serviceclients",
		"circlegatheringplan",
		"gathering_plan_service_client.g.go",
	)
	planPrivateAliasOutput := filepath.Join(
		outputRoot,
		"circle_management",
		"gathering_plan",
		"contract",
		"client",
		"gathering_plan_service_client.g.go",
	)
	planPathsOutput := filepath.Join(
		outputRoot,
		"serviceclients",
		"circle_gathering_plan_paths.g.go",
	)
	planCount, err := generateGatheringPlanServiceClient(
		source,
		planPublicClientOutput,
		planPrivateAliasOutput,
		planPathsOutput,
		false,
	)
	if err != nil {
		t.Fatalf("generate GatheringPlan service client: %v", err)
	}
	if planCount != len(expectedPlanOperations) {
		t.Fatalf(
			"generated GatheringPlan operation count=%d, want %d",
			planCount,
			len(expectedPlanOperations),
		)
	}
	planClient, err := os.ReadFile(planPublicClientOutput)
	if err != nil {
		t.Fatalf("read generated GatheringPlan client: %v", err)
	}
	for _, needle := range []string{
		"type ProposeGatheringPlanCommand struct",
		"type GatheringPlanCommandResult struct",
		"func EncodeGetGatheringPlan(",
		"func EncodeProposeGatheringPlan(",
		"func EncodeCommitGatheringPlanProposal(",
	} {
		if !strings.Contains(string(planClient), needle) {
			t.Errorf("generated GatheringPlan client missing %q", needle)
		}
	}
	planPaths, err := os.ReadFile(planPathsOutput)
	if err != nil {
		t.Fatalf("read generated GatheringPlan paths: %v", err)
	}
	for _, needle := range []string{
		"CircleGatheringPlanProposeGatheringPlanOperationID",
		"CircleGatheringPlanGetGatheringPlanPath",
		"CircleGatheringPlanOperationMetadata",
	} {
		if !strings.Contains(string(planPaths), needle) {
			t.Errorf("generated GatheringPlan paths missing %q", needle)
		}
	}
	if strings.Contains(string(planClient), "services/circle-service/") {
		t.Fatal("public GatheringPlan client imported Circle internal/generated code")
	}
}

func TestCircleDomainGenerationPlansFollowDeclaredCapabilities(t *testing.T) {
	t.Parallel()

	if plans, err := circleDomainGenerationPlans(nil); err == nil || plans != nil {
		t.Fatalf("nil source must fail closed: plans=%v err=%v", plans, err)
	}
	empty := contractcodegen.NewSourceFromGraph(".", &graph.ContractGraph{})
	if plans, err := circleDomainGenerationPlans(empty); err != nil || len(plans) != 0 {
		t.Fatalf("empty graph must produce no plans: plans=%v err=%v", plans, err)
	}

	objectPath := "circle/circle_management/sample/object.yaml"
	fieldsPath := "circle/circle_management/sample/fields.yaml"
	eventsPath := "circle/circle_management/sample/events.yaml"
	objects := []ast.Object{
		{
			ID:         "circle.sample",
			Domain:     "circle",
			Name:       "Sample",
			Kind:       ast.ObjectKindAggregateRoot,
			SourcePath: objectPath,
		},
		{
			ID:         "circle.sample_view",
			Domain:     "circle",
			Name:       "SampleView",
			Kind:       ast.ObjectKindProjection,
			SourcePath: "circle/circle_management/sample_view/object.yaml",
		},
		{
			ID:         "circle.unknown",
			Domain:     "circle",
			Name:       "Unknown",
			Kind:       ast.ObjectKind("unknown"),
			SourcePath: "circle/circle_management/unknown/object.yaml",
		},
	}
	source := contractcodegen.NewSourceFromGraph(".", &graph.ContractGraph{
		Objects: objects,
		Documents: []ast.SourceDocument{
			{Path: objectPath},
			{Path: fieldsPath},
			{Path: "circle/circle_management/sample_view/object.yaml"},
			{Path: "circle/circle_management/sample_view/fields.yaml"},
			{Path: "circle/circle_management/unknown/object.yaml"},
			{Path: "circle/circle_management/unknown/fields.yaml"},
		},
	})
	plans, err := circleDomainGenerationPlans(source)
	if err != nil {
		t.Fatalf("derive synthetic plans: %v", err)
	}
	if len(plans) != 1 || plans[0].Name != "Sample" ||
		!plans[0].GenerateModel || plans[0].GenerateEvents {
		t.Fatalf("plans=%+v, want one model-only Sample", plans)
	}

	withoutFields := contractcodegen.NewSourceFromGraph(".", &graph.ContractGraph{
		Objects: objects[:1],
		Documents: []ast.SourceDocument{
			{Path: objectPath},
			{Path: eventsPath},
		},
	})
	if plans, err := circleDomainGenerationPlans(withoutFields); err == nil || plans != nil {
		t.Fatalf(
			"events without fields must fail closed: plans=%v err=%v",
			plans,
			err,
		)
	}
}
