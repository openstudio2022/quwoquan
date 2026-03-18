/// 一级 Tab — 与 user_profile/ui_config.yaml profile_tabs 对齐
enum ProfileTab { creations, circles, interaction }

/// 创作二级 identity filter。
enum CreationSubTab { all, moment, work, micro, image, video, article }

/// 兼容旧状态结构保留，个人主页新 IA 已改为直接按内容类型筛选。
enum CreationWorkFormat { all, image, video, note }

/// 创作可见性过滤。
enum CreationVisibility { all, public_, private_ }

/// 互动子维度。
enum InteractionSubTab { likes, comments, shares }

/// 互动方向。
enum InteractionDirection { received, sent }

/// 兼容旧状态结构保留。
enum LifestyleSubTab { footprint, bookMovieMusic, taste, loveObject }
