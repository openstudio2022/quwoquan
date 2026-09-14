"""content-workbench CLI 接口。"""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from .http_server import serve
from .service import WorkbenchError,WorkbenchService

def _path(value,env,required=True):
    raw=value or os.environ.get(env)
    if required and not raw: raise WorkbenchError('CONTENT_WORKBENCH.ROOT_REQUIRED',f'{env} is required')
    return Path(raw).expanduser() if raw else None

def _service(args):
    forbidden=[Path(__file__).resolve().parents[4]]
    for env in ('QWQ_LIBRARY_ROOT','QWQ_CARRIED_MEDIA_ROOT'):
        if os.environ.get(env): forbidden.append(Path(os.environ[env]))
    return WorkbenchService(_path(args.publish_root,'QWQ_PUBLISH_ROOT'),_path(args.workbench_root,'QWQ_CONTENT_WORKBENCH_ROOT'),forbidden_roots=forbidden,staging_root=_path(getattr(args,'staging_root',None),'QWQ_CONTENT_WORKBENCH_STAGING_ROOT',False))

def handle_content_workbench(args):
    try:
        service=_service(args)
        if args.content_workbench_command=='serve':
            server=serve(service,Path(args.static_root),args.host,args.port); print(json.dumps({'url':f'http://{args.host}:{server.server_port}','readOnlyPublish':True,'snapshot':service.startup_stats()}),flush=True); server.serve_forever()
        elif args.content_workbench_command=='register-candidate':
            print(json.dumps(service.register_candidate({'objectId':args.object_id,'parentVersionId':args.parent_version,'versionId':args.version,'sourcePath':args.source_path}),ensure_ascii=False,indent=2))
        elif args.content_workbench_command=='query':
            print(json.dumps(service.query(),ensure_ascii=False,indent=2))
    except WorkbenchError as exc: raise SystemExit(f'[governance content-workbench] GATE_BLOCK {exc.code}: {exc}') from exc

def register_content_workbench_parser(sub):
    p=sub.add_parser('content-workbench',help='只读 canonical 内容池与独立离线复核台账')
    cmds=p.add_subparsers(dest='content_workbench_command',required=True)
    def roots(x):
        x.add_argument('--publish-root'); x.add_argument('--workbench-root'); x.add_argument('--staging-root')
    s=cmds.add_parser('serve'); roots(s); s.add_argument('--static-root',required=True); s.add_argument('--host',default='127.0.0.1'); s.add_argument('--port',type=int,default=0)
    r=cmds.add_parser('register-candidate'); roots(r); r.add_argument('--object-id',required=True); r.add_argument('--parent-version',choices=['R0','R1'],required=True); r.add_argument('--version',choices=['R1','R2'],required=True); r.add_argument('--source-path',required=True)
    q=cmds.add_parser('query'); roots(q)
