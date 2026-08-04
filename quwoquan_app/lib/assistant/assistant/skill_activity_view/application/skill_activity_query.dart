import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Skill 详情页单次活动窗口；服务端 cursor 是唯一分页真相源。
const int kAssistantSkillActivityDefaultLimit = 20;

/// Skill 活动联邦查询。返回值已经由服务端按 owner 授权脱敏，App 不解析
/// [SkillActivityView.sourceObjectRef] 恢复对象身份。
abstract class AssistantSkillActivityQuery {
  Future<SkillActivitySlice> listSkillActivities({
    required String skillId,
    String cursor = '',
    int limit = kAssistantSkillActivityDefaultLimit,
  });
}
