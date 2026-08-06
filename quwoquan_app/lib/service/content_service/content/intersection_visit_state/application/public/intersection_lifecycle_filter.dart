import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Default inbox lifecycle visibility for the canonical intersection reader.
const Set<String> defaultInboxHiddenLifecycleStates = <String>{
  'expired',
  'archived',
};

List<IntersectionReason> filterDefaultInboxLifecycle(
  List<IntersectionReason> items,
) {
  return items
      .where(
        (item) => !defaultInboxHiddenLifecycleStates.contains(
          item.lifecycleState.trim(),
        ),
      )
      .toList(growable: false);
}
