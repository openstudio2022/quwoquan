package skillcontext

import (
	"fmt"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
)

// RuntimeDescriptors declares the Reader adapters provided by assistant_run.
// The composition root must build one object-owned Catalog from this slice and
// pass that same Catalog to both DomainReaderDescriptor queries and
// NewRuntimeRegistry.
func RuntimeDescriptors() ([]readermodel.Descriptor, error) {
	descriptors := []readermodel.Descriptor{
		runDescriptor(
			"assistant.trigger_envelope",
			"trigger.envelope",
			[]string{"trigger"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityInternal,
			[]readermodel.SurfaceKind{
				readermodel.SurfacePersonal,
				readermodel.SurfaceShared,
			},
		),
		runDescriptor(
			"assistant.run_input",
			"turn.slot",
			[]string{"conversation", "device", "memory", "page", "temporal"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.run_preferences",
			"turn.preferences",
			[]string{"conversation", "memory"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.run_feedback_context",
			feedbackcontext.ResolverRef,
			[]string{"memory"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.skill_subscription_plan",
			"subscription.plan",
			[]string{"domain"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"account.user_interest_profile",
			"user.interest_profile",
			[]string{"memory"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"chat.conversation_context",
			"conversation.current_context",
			[]string{"conversation"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityInternal,
			[]readermodel.SurfaceKind{
				readermodel.SurfacePersonal,
				readermodel.SurfaceShared,
			},
		),
		publicObjectDescriptor(
			"circle.circle_context",
			CircleContextResolverRef,
			"circle-service",
			"circle.circle.GetCircle",
			"circle.CircleDetailQuery",
			"circle.Circle",
			15*60,
			60,
		),
		publicObjectDescriptor(
			"content.post_context",
			ContentContextResolverRef,
			"content-service",
			"content.post.GetPost",
			"content.ContentPostDetailQuery",
			"content.Post",
			5*60,
			30,
		),
		publicObjectDescriptor(
			"entity.homepage_context",
			EntityContextResolverRef,
			"entity-service",
			"entity.homepage.GetHomepageDetail",
			"entity.HomepageByIdQuery",
			"entity.Homepage",
			60*60,
			5*60,
		),
	}

	// Object-specific owner contracts override the assistant_run defaults by
	// stable resolver identity. Positional overrides would silently reassign a
	// sibling Reader whenever a new descriptor is inserted.
	for index := range descriptors {
		switch descriptors[index].ResolverRef {
		case "trigger.envelope":
			descriptors[index].MaxFreshnessSeconds = 60 * 60
		case "subscription.plan":
			descriptors[index].OwnerOperationRefs = []string{
				"assistant.skill_subscription.GetSkillSubscription",
			}
			descriptors[index].ObjectTypeRefs = []string{"assistant.SkillSubscription"}
		case "user.interest_profile":
			descriptors[index].OwnerService = "user-service"
			descriptors[index].OwnerOperationRefs = []string{
				"user.user_account.GetUserInterestProfile",
			}
			descriptors[index].ObjectTypeRefs = []string{"user.UserAccount"}
		case "conversation.current_context":
			descriptors[index].MaxFreshnessSeconds = 15 * 60
			descriptors[index].OwnerOperationRefs = []string{
				"assistant.assistant_run.GetAssistantRun",
			}
			descriptors[index].ObjectTypeRefs = []string{"chat.Conversation", "chat.Message"}
		}
	}

	result := make([]readermodel.Descriptor, 0, len(descriptors))
	for _, value := range descriptors {
		descriptor, err := readermodel.NewDescriptor(value)
		if err != nil {
			return nil, fmt.Errorf(
				"invalid context reader descriptor %q: %w",
				value.ResolverRef,
				err,
			)
		}
		result = append(result, descriptor)
	}
	return result, nil
}

func publicObjectDescriptor(
	descriptorID string,
	resolverRef string,
	ownerService string,
	ownerOperationRef string,
	inputSchemaRef string,
	objectTypeRef string,
	maxFreshnessSeconds int,
	cacheTTLSeconds int,
) readermodel.Descriptor {
	return readermodel.Descriptor{
		DescriptorID: descriptorID, ResolverRef: resolverRef,
		OwnerService:        ownerService,
		OwnerOperationRefs:  []string{ownerOperationRef},
		InputSchemaRef:      inputSchemaRef,
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{objectTypeRef},
		AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityPublic,
		MaxFreshnessSeconds: maxFreshnessSeconds,
		CacheTTLSeconds:     cacheTTLSeconds,
		SurfaceKinds: []readermodel.SurfaceKind{
			readermodel.SurfacePersonal,
			readermodel.SurfaceShared,
			readermodel.SurfacePublic,
		},
		ArtifactPolicy: readermodel.ArtifactInlineBounded,
		CitationPolicy: readermodel.CitationEntityReference,
	}
}

func runDescriptor(
	descriptorID string,
	resolverRef string,
	sourceKinds []string,
	authority generated.AssistantContextAuthority,
	sensitivity generated.AssistantContextSensitivity,
	surfaces []readermodel.SurfaceKind,
) readermodel.Descriptor {
	return readermodel.Descriptor{
		DescriptorID: descriptorID, ResolverRef: resolverRef,
		OwnerService: "assistant-service",
		OwnerOperationRefs: []string{
			"assistant.assistant_run.GetAssistantRun",
		},
		InputSchemaRef:      "assistant.GetAssistantRunQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"assistant.AssistantRun"},
		AcceptedSourceKinds: sourceKinds,
		Authority:           authority,
		Sensitivity:         sensitivity,
		SurfaceKinds:        surfaces,
		ArtifactPolicy:      readermodel.ArtifactInlineBounded,
		CitationPolicy:      readermodel.CitationSourceReference,
	}
}
