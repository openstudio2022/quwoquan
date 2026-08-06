import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class InMemoryContentReportQueryAdapter
    implements ContentMyReportsReader {
  InMemoryContentReportQueryAdapter(Iterable<MyReportItemSlice> items)
    : _items = List<MyReportItemSlice>.unmodifiable(items);

  final List<MyReportItemSlice> _items;

  @override
  Future<MyReportPageSlice> listMyReports(ContentMyReportsQuery query) async {
    final offset = _decodeOffset(query.cursor);
    final end = (offset + query.limit).clamp(0, _items.length);
    return MyReportPageSlice(
      items: _items.sublist(offset.clamp(0, _items.length), end),
      nextCursor: end < _items.length ? 'offset:$end' : null,
    );
  }

  static int _decodeOffset(String? cursor) {
    final value = cursor?.trim() ?? '';
    if (value.isEmpty) return 0;
    if (!value.startsWith('offset:')) {
      throw const FormatException('invalid alpha report cursor');
    }
    final parsed = int.tryParse(value.substring('offset:'.length));
    if (parsed == null || parsed < 0) {
      throw const FormatException('invalid alpha report cursor');
    }
    return parsed;
  }
}
