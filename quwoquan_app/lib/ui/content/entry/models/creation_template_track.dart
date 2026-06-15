import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

enum CreationTemplateTrackId {
  experience,
  guide,
  review,
  question,
  checklist,
  story,
}

@immutable
class CreationTemplatePrompt {
  const CreationTemplatePrompt({
    required this.id,
    required this.label,
    required this.helperText,
    required this.titlePlaceholder,
    required this.bodySkeleton,
    required this.suggestedIdentity,
    required this.articleTemplate,
  });

  final CreationTemplateTrackId id;
  final String label;
  final String helperText;
  final String titlePlaceholder;
  final String bodySkeleton;
  final CreateContentIdentity suggestedIdentity;
  final ArticleTemplatePreset articleTemplate;

  CreateEditorState applyTo(CreateEditorState state) {
    final title = state.title.trim().isEmpty ? titlePlaceholder : state.title;
    final body = state.body.trim().isEmpty ? bodySkeleton : state.body;
    return state.copyWith(
      editorKind: CreateEditorKind.text,
      mediaKind: CreateMediaKind.none,
      title: title,
      body: body,
      articleTemplate: articleTemplate,
      articleDocument: createDefaultArticleDocument(title: title, body: body),
    );
  }
}

const List<CreationTemplatePrompt> creationTemplateTracks =
    <CreationTemplatePrompt>[
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.experience,
        label: '经历分享',
        helperText: '把真实经历讲清楚：背景、过程、转折、收获。',
        titlePlaceholder: '我在这里的一次真实经历',
        bodySkeleton: '背景：\n\n发生了什么：\n\n最有用的细节：\n\n适合谁参考：',
        suggestedIdentity: CreateContentIdentity.moment,
        articleTemplate: ArticleTemplatePreset.gentle,
      ),
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.guide,
        label: '实用攻略',
        helperText: '帮助别人做决定：路线、预算、避坑、适合人群。',
        titlePlaceholder: '给第一次来这里的实用攻略',
        bodySkeleton: '适合谁：\n\n怎么安排：\n\n预算与时间：\n\n避坑提醒：',
        suggestedIdentity: CreateContentIdentity.work,
        articleTemplate: ArticleTemplatePreset.journal,
      ),
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.review,
        label: '体验评价',
        helperText: '从优点、限制和推荐场景说明你的判断。',
        titlePlaceholder: '这次体验值不值得去',
        bodySkeleton: '一句话结论：\n\n我喜欢的点：\n\n不适合的情况：\n\n推荐给：',
        suggestedIdentity: CreateContentIdentity.work,
        articleTemplate: ArticleTemplatePreset.ritual,
      ),
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.question,
        label: '提问求助',
        helperText: '说清楚你已经知道什么、卡在哪里、希望别人怎么帮。',
        titlePlaceholder: '想请教一个具体问题',
        bodySkeleton: '我想做什么：\n\n已经查到的信息：\n\n现在卡住的点：\n\n希望获得的帮助：',
        suggestedIdentity: CreateContentIdentity.moment,
        articleTemplate: ArticleTemplatePreset.gentle,
      ),
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.checklist,
        label: '清单整理',
        helperText: '把可复用的信息整理成清单，方便别人参考和执行。',
        titlePlaceholder: '一份可以直接照着用的清单',
        bodySkeleton: '准备清单：\n1. \n2. \n3. \n\n注意事项：\n\n适用场景：',
        suggestedIdentity: CreateContentIdentity.work,
        articleTemplate: ArticleTemplatePreset.journal,
      ),
      CreationTemplatePrompt(
        id: CreationTemplateTrackId.story,
        label: '故事记录',
        helperText: '用人物、场景和细节讲一个有温度的故事。',
        titlePlaceholder: '那天发生的一件小事',
        bodySkeleton: '故事发生在：\n\n我记住的一个画面：\n\n后来我意识到：\n\n想分享给谁：',
        suggestedIdentity: CreateContentIdentity.moment,
        articleTemplate: ArticleTemplatePreset.journal,
      ),
    ];

CreationTemplatePrompt creationTemplateTrackById(CreationTemplateTrackId id) {
  return creationTemplateTracks.firstWhere((track) => track.id == id);
}
