import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/application/user/persona_relationship/persona_relationship_facets.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_edit_snapshot_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_view_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

import '../alpha_fixture_user_resolver.dart';
import '../../object_scenario_seed_reader.dart';

part 'src/alpha_user_profile_contract_seed_helpers.dart';
part 'src/alpha_user_profile_repository_helpers.dart';
part 'src/alpha_user_profile_relationship_normalization.dart';
part 'src/alpha_user_profile_repository_impl.dart';

typedef _ProfileEditSnapshotOverrideMap =
    Map<String, ProfileEditSnapshotWireDto>;

String get kMockCurrentOwnerId =>
    AlphaFixtureUserResolver.currentUserVariantUserId;

String get kMockCurrentPersonaId =>
    AlphaFixtureUserResolver.currentUserVariantPersonaId;
