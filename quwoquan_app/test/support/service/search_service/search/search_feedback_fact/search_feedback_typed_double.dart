import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/application/public/search_feedback_command_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
/// SearchFeedbackFact append 对象级替身。
///
/// 服务端以 (searchRequestId,eventType,objectId) 去重；替身使用同一语义键，
/// 保证重放不会产生第二条事实。
final class SearchFeedbackTypedDouble implements SearchFeedbackCommandWriter {
  final Map<String, ReportSearchFeedbackCommand> _records =
      <String, ReportSearchFeedbackCommand>{};

  List<ReportSearchFeedbackCommand> get recorded =>
      _records.values.toList(growable: false);

  @override
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  ) async {
    final key =
        '${command.searchRequestId}\u0000${command.eventType.wireValue}\u0000'
        '${command.objectId ?? ''}';
    _records.putIfAbsent(key, () => command);
    return const SearchFeedbackAck(
      accepted: true,
      requestId: 'alpha-search-feedback',
    );
  }
}
