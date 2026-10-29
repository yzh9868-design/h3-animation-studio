"""Configure/import/list/check ComfyUI workflows. Never submits GPU work."""
from pathlib import Path
import argparse
import json
import sys

import comfy_config as config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=config.SKILL,
                        help='Skill directory containing profiles/ and private local/ configuration')
    actions = parser.add_subparsers(dest='action', required=True)
    command = actions.add_parser('configure', help='Save private local connection settings')
    command.add_argument('--url')
    command.add_argument('--profile')
    command.add_argument('--timeout', type=float)
    command.add_argument('--header-env', action='append', metavar='HEADER=ENVVAR')
    command.add_argument('--width', type=int, help='Expected output width; preserves upstream size-selector links')
    command.add_argument('--height', type=int, help='Expected output height; preserves upstream size-selector links')
    command = actions.add_parser('import-workflow', help='Register a copied API-format workflow without running it')
    command.add_argument('file', type=Path)
    command.add_argument('--name', required=True)
    command.add_argument('--mapping', type=Path, help='JSON profile fields to override inferred bindings/defaults')
    command.add_argument('--replace', action='store_true')
    actions.add_parser('list', help='List registered generation workflows and configuration status')
    actions.add_parser('apis', help='List ComfyUI transport endpoints, distinct from workflow profiles')
    command = actions.add_parser('doctor', help='Check configuration; networking requires --online')
    command.add_argument('--profile')
    command.add_argument('--online', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'configure':
        headers = None
        if args.header_env is not None:
            headers = {}
            for value in args.header_env:
                if '=' not in value:
                    parser.error('--header-env requires HEADER=ENVVAR, not a credential')
                key, variable = value.split('=', 1)
                headers[key] = variable
        result = config.configure(args.root, url=args.url, profile=args.profile, timeout=args.timeout,
                                  headers_env=headers, width=args.width, height=args.height)
    elif args.action == 'import-workflow':
        result = config.import_workflow(args.root, args.file, args.name, args.mapping, args.replace)
    elif args.action == 'list':
        result = config.list_workflows(args.root)
    elif args.action == 'apis':
        result = {'http_apis': config.HTTP_APIS, 'network_requests': 0, 'gpu_submission': False,
                  'note': 'These are transport endpoints, not registered generation workflows.'}
    else:
        result = config.doctor(args.root, args.profile, args.online)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.action == 'doctor' and result['status'] == 'needs_configuration' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({'error': str(error), 'gpu_submission': False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
