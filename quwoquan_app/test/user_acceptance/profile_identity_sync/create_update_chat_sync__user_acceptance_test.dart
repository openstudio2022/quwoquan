import '../../cloud/chat/chat_message_snapshot_contract_test.dart'
    as chat_message_snapshot_contract;
import '../../ui/user/journeys/edit_profile_journey_test.dart'
    as edit_profile_journey;
import '../../ui/user/journeys/my_profile_journey_test.dart'
    as my_profile_journey;

void main() {
  my_profile_journey.main();
  edit_profile_journey.main();
  chat_message_snapshot_contract.main();
}
