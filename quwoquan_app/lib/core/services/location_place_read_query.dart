import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart'
    show SearchObjectType;

/// Canonical `location.place` read result for direct routes and recovery.
///
/// It intentionally reuses [SearchLocationPlaceHitView], the only App view of
/// an unpromoted place. A homepage hit is a terminal redirect, not a second
/// place-shaped payload.
sealed class LocationPlaceReadResult {
  const LocationPlaceReadResult();
}

final class LocationPlaceReadFound extends LocationPlaceReadResult {
  const LocationPlaceReadFound(this.place);

  final SearchLocationPlaceHitView place;
}

final class LocationPlaceReadHomepageRedirect extends LocationPlaceReadResult {
  const LocationPlaceReadHomepageRedirect({required this.homepageId});

  final String homepageId;
}

final class LocationPlaceReadUnavailable extends LocationPlaceReadResult {
  const LocationPlaceReadUnavailable();
}

abstract interface class LocationPlaceReadQuery {
  Future<LocationPlaceReadResult> readById(String placeId);
}

/// Uses the canonical Search read transport with an explicit `ids` match.
///
/// `location.place` and `entity.homepage` stay mutually exclusive in the
/// result, so a promoted location can be redirected without fabricating place
/// details from a stale deep-link.
final class SearchLocationPlaceReadQuery implements LocationPlaceReadQuery {
  const SearchLocationPlaceReadQuery({required this.search});

  final SearchRepository search;

  @override
  Future<LocationPlaceReadResult> readById(String placeId) async {
    final normalizedId = placeId.trim();
    if (normalizedId.isEmpty) {
      return const LocationPlaceReadUnavailable();
    }
    final response = await search.search(
      SearchRequest(
        query: normalizedId,
        mode: SearchMode.result,
        ids: <String>[normalizedId],
        objectTypes: const <SearchObjectType>{
          SearchObjectType.locationPlace,
          SearchObjectType.entityHomepage,
        },
        limit: 2,
      ),
    );
    for (final hit in response.hits) {
      final place = hit.asLocationPlaceItem;
      if (place != null && place.placeId == normalizedId) {
        return LocationPlaceReadFound(place);
      }
    }
    for (final hit in response.hits) {
      final homepage = hit.asEntityHomepageItem;
      if (homepage != null && homepage.homepageId.trim().isNotEmpty) {
        return LocationPlaceReadHomepageRedirect(
          homepageId: homepage.homepageId.trim(),
        );
      }
    }
    return const LocationPlaceReadUnavailable();
  }
}
