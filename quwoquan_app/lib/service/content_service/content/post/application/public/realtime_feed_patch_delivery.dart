import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Stable feed-patch sink consumed by the realtime connection object.
abstract interface class RealtimeFeedPatchSink {
  void apply(FeedRealtimePatch patch);
}

FeedRealtimePatch decodeRealtimeFeedPatch(Map<String, dynamic> wire) {
  return parseFeedRealtimePatch(wire);
}
