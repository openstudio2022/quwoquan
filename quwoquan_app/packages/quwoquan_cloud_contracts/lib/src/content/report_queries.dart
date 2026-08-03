import 'content_operation_contracts.g.dart';

abstract interface class ContentMyReportQueryFacet {
  Future<MyReportPageSlice> listMyReports(ContentMyReportsQuery query);
}
