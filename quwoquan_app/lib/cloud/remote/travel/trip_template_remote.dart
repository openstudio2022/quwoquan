import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_template_facet.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_share_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripTemplateFacet implements TripTemplateFacet {
  const RemoteTripTemplateFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripPlanTemplate> createTemplate(
    CreateTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanTemplateCreateTripPlanTemplate(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.createTripPlanTemplate,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripPlanTemplateListSlice> listTemplates() {
    return client.travelTripPlanTemplateListTripPlanTemplates(
      const ListTripPlanTemplatesQuery(),
      context: invocationContext(
        AppUiSurfaces.travelTemplates,
        TravelRequestPageIds.listTripPlanTemplates,
      ),
    );
  }

  @override
  Future<TripPlanTemplate> reviseTemplate(
    PutTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanTemplateReviseTripPlanTemplate(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTemplates,
        TravelRequestPageIds.reviseTripPlanTemplate,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
