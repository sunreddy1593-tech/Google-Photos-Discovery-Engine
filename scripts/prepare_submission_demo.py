"""Fresh local demo plus a curated, secrets-free Streamlit Cloud package."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.export.build import build_submission
from src.export.reference import build_reference
from src.export.privacy import leak_findings
from src.models.export import PublicExportRecord


def prepare(root: Path, output: Path, package: Path) -> dict:
    if output.exists() or package.exists() or package.with_suffix('.zip').exists():
        raise ValueError('All destinations must be fresh')
    index=build_submission(root/'config/submission_manifest.json',output,root=root)
    reference=build_reference(root/'data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02',output/'approved-reference')
    index['approved_reference_export']='approved-reference'
    (output/'index.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
    package.mkdir(parents=True)
    files=['app.py','community_insights.py','src/__init__.py','src/core/__init__.py',
           'src/core/versions.py','src/core/ids.py','src/export/__init__.py',
           'src/export/load.py','src/export/compare.py','src/export/present.py',
           'src/export/privacy.py','src/export/reference.py','src/export/scheduled_status.py',
           'src/export/reviewed_reference.py','src/export/reference_standard.py']
    files += [p.relative_to(root).as_posix() for p in (root/'src/models').glob('*.py')]
    if (root/'.streamlit/config.toml').is_file(): files.append('.streamlit/config.toml')
    for name in files:
        target=package/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,target)
    (package/'requirements.txt').write_text('streamlit==1.65.0\npydantic>=2.8,<3\n',encoding='utf-8')
    shutil.copytree(output/'approved-reference',package/'data/exports/submission/approved-reference')
    # Human-reviewed n8n reference (immutable artifact) and the published automated
    # comparison snapshot. Both are already public-profile files; neither carries raw text.
    reviewed=root/'data/exports/reference/n8n-reviewed-reference-01'
    if reviewed.is_dir():
        shutil.copytree(reviewed,package/'data/exports/reference/n8n-reviewed-reference-01')
    standard=root/'data/exports/public/reference-standard-snapshot'
    if (standard/'CURRENT.json').is_file():
        shutil.copytree(standard,package/'data/exports/public/reference-standard-snapshot')
    folder=package/'data/exports/submission/reviewed-development-reference'
    folder.mkdir()
    description='Ten reviewed development documents and six human-approved reference cases. Model predictions are not included; separate quality aggregates retain actual measured coverage.'
    summary={'dataset_id':'reviewed-development-reference','description':description,'documents':10,
             'reference_cases':6,'stored_cases':0,'automatically_valid_cases':0,'semantically_approved_cases':0,
             'analysis_documents':10,'extraction_attempts':0,'failed_attempts':0,'empty_responses':0,
             'unresolved_review_items':0,'limitations':reference['limitations']}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    public_index={'submission_id':'public-demo-2026-10-04','approved_reference_export':'approved-reference',
        'datasets':[{'dataset_id':'reviewed-development-reference','description':description,
                     'run_id':'reference-02','split_policy':'development_only','limitations':reference['limitations']}],
        'not_combined':['Reference labels are not model outputs. Quality aggregates use separate measurements.'],
        'semantic_risks':index['semantic_risks']}
    (package/'data/exports/submission/index.json').write_text(json.dumps(public_index,indent=2)+'\n',encoding='utf-8')
    quality=json.loads((root/'data/exports/quality/CURRENT.json').read_text(encoding='utf-8'))
    safe={k:v for k,v in quality.items() if isinstance(v,(int,float,bool,type(None)))}
    for key in ('status','numeric_gate_status','m1_status','limitations','splits','accepted_limitations'):
        if key in quality: safe[key]=quality[key]
    path=package/'data/exports/quality/CURRENT.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8')
    integration={'implementation':'bridge and inactive workflow prepared; mocked tests only',
        'live_connection':'not configured or exercised in this session',
        'source_access':'not verified; unsupported or blocked pages fail closed',
        'replies':'not fetched; completeness false','last_import_documents':0}
    for base in (root,package):
        path=base/'data/exports/public/integration-status.json'
        if base==root and path.exists(): continue
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(integration,indent=2)+'\n',encoding='utf-8')
    (package/'README.md').write_text(
        '# Discovery engine demonstration\n\nRun `python -m streamlit run app.py`.\n\n'
        'Streamlit Community Cloud: select Python 3.12, app.py and requirements.txt. No secrets are required. '
        'Only reviewed development reference excerpts and aggregate evaluation results are included. '
        'Original sources, holdout packets, annotations, credentials and provider payloads remain local. '
        'Six reference cases do not mean six successful model extractions. The v3 development baseline matches 2/6; '
        'the separate v4 experiment matches 4/6, with five accepted cases and unresolved semantic errors. '
        'holdout coverage 5/15 on previously exposed seats. No independent second coder or prevalence estimate.\n',encoding='utf-8')
    hashes={}
    for path in sorted(package.rglob('*')):
        if not path.is_file(): continue
        hashes[path.relative_to(package).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix=='.json' and leak_findings(json.loads(path.read_text(encoding='utf-8'))):
            raise ValueError('Public metadata failed privacy scan')
        if path.suffix=='.jsonl':
            reviewed_reference='data/exports/reference/' in path.relative_to(package).as_posix()
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip(): continue
                if reviewed_reference:
                    # n8n reviewed records are not PublicExportRecord rows; scan them for leaks only.
                    if leak_findings(json.loads(line)):
                        raise ValueError('Reviewed reference record failed privacy scan')
                    continue
                record=PublicExportRecord.model_validate_json(line)
                if leak_findings(record.model_dump(mode='json')):
                    raise ValueError('Public evidence failed privacy scan')
    audit={'public_records':reference['evidence_fragments'],'unique_reference_cases':reference['cases'],
           'holdout_text_included':False,'provider_calls':0,'requires_secrets':False,'file_sha256':hashes}
    (package/'package-audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(package.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(package).as_posix())
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(ROOT,args.output.resolve(),args.package.resolve())
    print(json.dumps({k:result[k] for k in ('public_records','unique_reference_cases','provider_calls','requires_secrets')},indent=2))
