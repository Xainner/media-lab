"""Vendor official Animate UI registry components and their registry dependencies."""
import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'src'
seen = set()


def install(name):
    if name in seen:
        return
    seen.add(name)
    animate = name.startswith('@animate-ui/')
    slug = name.split('/')[-1]
    url = f'https://animate-ui.com/r/{slug}.json' if animate else f'https://ui.shadcn.com/r/styles/new-york/{slug}.json'
    with urllib.request.urlopen(url, timeout=45) as response:
        data = json.load(response)
    for dependency in data.get('registryDependencies', []):
        install(dependency)
    for item in data.get('files', []):
        target = item.get('target')
        if not target:
            folder = 'hooks' if item.get('type') == 'registry:hook' else 'components/ui'
            target = folder + '/' + Path(item['path']).name
        destination = root / target.replace('~/', '')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Vendored files include React 18 compatibility fixes. Preserve local adaptations.
        if not destination.exists():
            destination.write_text('// Source: ' + url + '\n// Animate UI: MIT + Commons Clause; shadcn/ui: MIT. See public/licenses.\n' + item['content'], encoding='utf-8')
        print(destination.relative_to(root), flush=True)


for component in ('sidebar', 'dialog', 'tabs', 'sheet', 'dropdown-menu', 'accordion', 'progress'):
    install('@animate-ui/components-radix-' + component)
install('@animate-ui/components-buttons-button')
install('@animate-ui/components-animate-tooltip')
