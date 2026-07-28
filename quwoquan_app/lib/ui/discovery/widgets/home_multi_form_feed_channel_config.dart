part of 'home_multi_form_feed.dart';

extension _HomeMultiFormFeedChannelConfig on HomeMultiFormFeed {
  String _resolveChannelMoodCopy() {
    for (final channel in ContentUIConfig.homeChannels) {
      if (channel.id == channelId) {
        return UITextConstants.homeChannelMoodCopy(channel.moodCopyKey);
      }
    }
    return '';
  }

  HomeChannelConfig? _resolveChannelConfig() {
    for (final channel in ContentUIConfig.homeChannels) {
      if (channel.id == channelId) {
        return channel;
      }
    }
    return null;
  }
}
