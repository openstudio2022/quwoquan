part of 'home_multi_form_feed.dart';

extension _HomeMultiFormFeedChannelConfig on HomeMultiFormFeed {
  HomeChannelConfig? _resolveChannelConfig(WidgetRef ref) {
    for (final channel in ref.watch(homeChannelsProvider)) {
      if (channel.id == channelId) {
        return channel;
      }
    }
    return null;
  }
}
