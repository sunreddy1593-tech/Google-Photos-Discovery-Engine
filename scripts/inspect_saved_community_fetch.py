"""Offline shape inspection; decode string data without executing page scripts."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def js_string(encoded):
    result = []
    cursor = 0
    escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
               '\\': '\\', "'": "'", '"': '"', '/': '/'}
    while cursor < len(encoded):
        char = encoded[cursor]
        cursor += 1
        if char != '\\':
            result.append(char)
            continue
        char = encoded[cursor]
        cursor += 1
        if char in ('x', 'u'):
            width = 2 if char == 'x' else 4
            result.append(chr(int(encoded[cursor:cursor + width], 16)))
            cursor += width
        elif char in escapes:
            result.append(escapes[char])
        else:
            raise ValueError('Unsupported escape')
    return ''.join(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    exported = json.loads(args.input.read_text(encoding='utf-8-sig'))
    html = exported[0]['json']['html']
    print(json.dumps({'sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
                      'html_characters': len(html)}))
    declarations = re.finditer(r"\bvar\s+(\w+)\s*=\s*'((?:\\[\s\S]|[^'\\])*)'", html)
    for match in declarations:
        try:
            decoded = json.loads(js_string(match[2]))
        except ValueError:
            continue
        if match[1] != 'thread_view':
            continue
        print('Bootstrap variable:', match[1])
        def walk(value, path, depth):
            if isinstance(value, list):
                if depth <= 2:
                    print(json.dumps({'path': path, 'type': 'array', 'length': len(value)}))
                for index, item in enumerate(value):
                    walk(item, path + [index], depth + 1)
            elif isinstance(value, str):
                if '<' in value or 'Screenshot' in value:
                    print(json.dumps({'path': path, 'type': 'string', 'characters': len(value),
                                      'has_markup': '<' in value, 'is_thread_title': 'Screenshot' in value}))
            elif value == 106429666 or (path[:1] == [1] and isinstance(value, int)):
                print(json.dumps({'path': path, 'type': type(value).__name__, 'value': value}))
        walk(decoded, [], 0)


if __name__ == '__main__':
    main()
