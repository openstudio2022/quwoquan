import 'package:quwoquan_app/personal_assistant/cost/assistent_cost_ledger.dart';

class AssistentCostApi {
  const AssistentCostApi(this._ledger);

  final AssistentCostLedger _ledger;

  Future<Map<String, dynamic>> dashboard() async {
    final summary = await _ledger.summary();
    final recent = await _ledger.listRecent(limit: 100);
    return <String, dynamic>{
      'summary': summary.toJson(),
      'recent': recent.map((record) => record.toJson()).toList(growable: false),
    };
  }
}

