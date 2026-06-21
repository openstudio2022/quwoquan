import '../../cloud/user/contract/user_repository_contract_test.dart'
    as user_repository_contract;
import '../../ui/user/journeys/persona_management_journey_test.dart'
    as persona_management_journey;
import '../../ui/user/providers/persona_management_provider_test.dart'
    as persona_management_provider;
import '../../ui/user/widgets/persona_management_page_test.dart'
    as persona_management_page;

void main() {
  user_repository_contract.main();
  persona_management_provider.main();
  persona_management_page.main();
  persona_management_journey.main();
}
