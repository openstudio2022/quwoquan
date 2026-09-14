export type RendererKind='homepage'|'article'|'image'|'video'|'unknown';
const registry:Record<string,RendererKind>={homepage:'homepage',article:'article',image:'image',video:'video'};
export function rendererFor(contentFormId:string):RendererKind{return registry[contentFormId]??'unknown';}
export function validateReview(input:{state:string;changes?:string;targetState?:string}):string[]{const errors:string[]=[];if(!['qualified','unqualified'].includes(input.state))errors.push('请选择人工结论');if(input.state==='unqualified'){if(!input.changes?.trim())errors.push('不合格必须填写修改要求');if(!input.targetState?.trim())errors.push('不合格必须选择目标状态');}return errors;}
