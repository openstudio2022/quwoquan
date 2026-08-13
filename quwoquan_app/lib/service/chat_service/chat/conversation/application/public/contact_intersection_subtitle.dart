import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ContactIntersectionFact;

/// typed 交集事实（≤2 条）的联系人 subtitle 拼装：只透传云侧 primaryText，
/// 端不拼句不改写。conversation 对象拥有该展示拼装规则，组合根只引用。
String contactIntersectionFactsSubtitle(List<ContactIntersectionFact> facts) =>
    facts
        .take(2)
        .map((fact) => fact.primaryText.trim())
        .where((text) => text.isNotEmpty)
        .join(' · ');
