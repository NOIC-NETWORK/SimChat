# -*- coding: utf-8 -*-
"""录制 Agent SSE 事件，把推导版 fixture 替换成真实 trace。

用法：
    python simchat/fixtures/record_agent_sse.py --message "列出所有 Markdown 文件" \
        --out simchat/fixtures/agent-happy.recorded.json

    # 需要覆盖审批链路时：
    python simchat/fixtures/record_agent_sse.py --message "写入 digest.md" \
        --decision approve --out simchat/fixtures/agent-approval.recorded.json

前提：LMBrewer 已启动，且模型后端（Ollama / JRVS-7B）可用。
只依赖标准库；不引入 requests。
"""
import argparse
import datetime
import json
import sys
import urllib.request


def _post_sse(url, body):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url, data=data, method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
    )
    events = []
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode('utf-8', errors='replace').rstrip('\n')
            if not line.startswith('data:'):
                continue          # 跳过 keepalive 注释行与空行
            payload = line[5:].strip()
            if not payload:
                continue
            evt = json.loads(payload)
            events.append(evt)
            print(json.dumps(evt, ensure_ascii=False))
            if evt.get('event') in ('final', 'aborted', 'error', 'max_turns', 'approval_required'):
                break
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--prefix', default='/api/kirara', help='当前用 /api/kirara；Phase 2 后可用 /api/simchat')
    parser.add_argument('--message', required=True)
    parser.add_argument('--session-id', default=None)
    parser.add_argument('--decision', choices=['approve', 'reject'], default=None)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    session_id = args.session_id or 'agent_recorded_' + datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    run_body = {'message': args.message, 'history': [], 'session_id': session_id}
    run_url = args.base_url.rstrip('/') + args.prefix + '/agent/run'

    streams = [{
        'step': 'run',
        'http': {'method': 'POST', 'path': args.prefix + '/agent/run', 'body': run_body},
        'events': _post_sse(run_url, run_body),
    }]

    if args.decision and streams[0]['events']:
        run_id = streams[0]['events'][0].get('run_id')
        if not run_id:
            print('未拿到 run_id，无法审批', file=sys.stderr)
            return 2
        approve_body = {'run_id': run_id, 'decision': args.decision}
        approve_url = args.base_url.rstrip('/') + args.prefix + '/agent/approve'
        streams.append({
            'step': 'approve',
            'http': {'method': 'POST', 'path': args.prefix + '/agent/approve', 'body': approve_body},
            'events': _post_sse(approve_url, approve_body),
        })

    fixture = {
        'name': args.out.rsplit('/', 1)[-1].rsplit('\\', 1)[-1].replace('.json', ''),
        'contract': 'lmbrew-mod/1',
        'source': 'recorded',
        'captured_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'config': {'base_url': args.base_url, 'prefix': args.prefix, 'session_id': session_id},
        'streams': streams,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    print('\n已写入 ' + args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
