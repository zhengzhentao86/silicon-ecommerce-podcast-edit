"""检查技能发布文件、入口、相对引用和意外私人材料；仅使用标准库。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
NAME = 'silicon-ecommerce-podcast-edit'
FORBIDDEN_SUFFIXES = {'.wav','.mp3','.m4a','.flac','.mp4','.mov','.sqlite','.db','.pem','.key'}
PATTERNS = [
    re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    re.compile(r'[A-Za-z]:\\(?:Users|Documents)\\[A-Za-z0-9_.-]+\\'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{30,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def candidate_files():
    result = subprocess.run(['git','-C',str(ROOT),'ls-files','--cached','-z'],capture_output=True,check=True)
    files = [ROOT/p for p in result.stdout.decode().split('\0') if p]
    if files:
        return files
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
        and not {'.git','.venv','__pycache__'}.intersection(p.relative_to(ROOT).parts))


def validate():
    files = candidate_files()
    errors, links = [], 0
    required = ['SKILL.md','agents/openai.yaml','references/show-profile.md',
        'references/workflow.md','references/audio-contract.md','scripts/cut_plan.py',
        'scripts/render_cut.py','scripts/test_cut_plan.py','scripts/test_render_cut.py',
        'README.md','CONTRIBUTING.md','LICENSE','requirements.txt',
        'assets/podcast-project.example.json','.github/workflows/ci.yml']
    for relative in required:
        if not (ROOT/relative).is_file():
            errors.append(f'缺少文件：{relative}')
    entry = (ROOT/'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'\A---\n(.*?)\n---\n',entry,re.S)
    if not match or not re.search(r'^name:\s*'+re.escape(NAME)+r'\s*$',match.group(1),re.M):
        errors.append('技能入口名称或frontmatter不符')
    if not match or not re.search(r'^description:\s*\S',match.group(1),re.M):
        errors.append('缺少触发description')
    if '[TODO:' in entry:
        errors.append('入口仍有未完成占位符')
    ui = (ROOT/'agents/openai.yaml').read_text(encoding='utf-8')
    if '$'+NAME not in ui or '硅基新电商播客剪辑' not in ui:
        errors.append('UI名称或调用标识缺失')
    for path in files:
        relative = str(path.relative_to(ROOT))
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.startswith('.env'):
            errors.append(f'发布清单含私有材料类型：{relative}')
            continue
        if path.stat().st_size>1024*1024:
            errors.append(f'发布文件意外过大：{relative}')
            continue
        content = path.read_text(encoding='utf-8')
        if any(pattern.search(content) for pattern in PATTERNS):
            # 不复述疑似敏感值。
            errors.append(f'发布文件含本机路径或疑似凭据：{relative}')
        if path.suffix=='.py':
            ast.parse(content,filename=relative)
        if path.suffix=='.json':
            json.loads(content)
        if path.suffix=='.md':
            for target in re.findall(r'\]\(([^)]+)\)',content):
                if target.startswith(('https://','http://','#')):
                    continue
                resolved = (path.parent/target.split('#')[0]).resolve()
                if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
                    errors.append(f'相对引用不存在或越出仓库：{relative}')
                links += 1
    if errors:
        raise ValueError('\n'.join(errors))
    return {'release_files_checked':len(files),'relative_references_checked':links,
        'entry_and_scripts_valid':True,'private_material_checks_passed':True}


if __name__=='__main__':
    print(json.dumps(validate(),ensure_ascii=False))
