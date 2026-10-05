"""Synthetic approved-reference export tests and public package UI checks."""
from pathlib import Path
import json

import pytest
from streamlit.testing.v1 import AppTest
from src.export.reference import build_reference, reference_comparison
from src.models.gold import GoldDocumentLabel
from src.gold.annotate import _cases_from_review

pytestmark=pytest.mark.synthetic


def fixture(root):
    pack=root/'starter/reviewed'
    (pack/'development-reference-02').mkdir(parents=True)
    (pack/'labels/Sunayana').mkdir(parents=True)
    (pack.parent/'packets').mkdir()
    source='A public picnic post. I found it. Other context is withheld.'
    quote='I found it.'; start=source.index(quote)
    case={'ordinal':1,'expected_values':{'outcome':{'observation':'stated','value':'found'}},
          'evidence':[{'field_name':'outcome','quote':quote,'start_char':start,'end_char':start+len(quote)}]}
    review={'doc_id':'synthetic-doc','split':'dev','cases':[case]}
    packet={'gold_split':'dev','source_text':source,'provenance':{'source_platform':'google_support',
        'source_type':'support_thread','evidence_tier':'synthetic_test','source_name':'Synthetic fixture',
        'source_url':'https://support.google.com/photos/thread/999'}}
    (pack/'labels/Sunayana/synthetic-doc.json').write_text(json.dumps(review))
    (pack.parent/'packets/synthetic-doc.json').write_text(json.dumps(packet))
    doc=GoldDocumentLabel(doc_id='synthetic-doc',split='dev',scope_class='adjacent_known_item_retrieval',
        reason_code='known_item_retrieval_journey_described',prefilter_should_pass=True,
        expected_case_count=1,labeler_id='Sunayana',labeled_at='2026-10-04T00:00:00Z')
    gold=pack/'development-reference-02'
    (gold/'documents.jsonl').write_text(doc.model_dump_json()+'\n')
    cases=_cases_from_review('synthetic-doc',[case],source,labeler_id='Sunayana')
    (gold/'cases.jsonl').write_text(''.join(c.model_dump_json()+'\n' for c in cases))
    return pack,source


def test_reference_minimum_excerpt_offsets_and_no_model_approval(tmp_path):
    pack,source=fixture(tmp_path)
    out=tmp_path/'public'
    before=(pack/'development-reference-02/cases.jsonl').read_bytes()
    result=build_reference(pack,out)
    row=json.loads((out/'cases.jsonl').read_text())
    assert row['excerpt']=='I found it.' and row['excerpt']!=source
    assert row['evidence_spans'][0]['excerpt_start_char']==0
    assert source[row['excerpt_start_char']:row['excerpt_start_char']+len(row['excerpt'])]==row['excerpt']
    assert row['extracted_fields']['model_output'] is False
    assert result['cases']==1 and result['model_outputs_approved'] is False
    assert (pack/'development-reference-02/cases.jsonl').read_bytes()==before
    assert reference_comparison(result)['outcome']['rows'][0]['cases']==['synthetic-doc#g01']


def test_reference_refuses_holdout_and_value_changes(tmp_path):
    pack,_=fixture(tmp_path)
    path=pack.parent/'packets/synthetic-doc.json'
    packet=json.loads(path.read_text()); packet['gold_split']='holdout'
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError,match='Holdout'):
        build_reference(pack,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_reference_app_and_saved_search(tmp_path):
    from tests.test_submission_export import _fixture
    from src.export.build import build_submission
    pack,_=fixture(tmp_path/'reference-input')
    out=tmp_path/'reference'; build_reference(pack,out)
    baseline=tmp_path/'baseline'; baseline.mkdir()
    demo=tmp_path/'demo'; build_submission(_fixture(baseline),demo,root=baseline)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
    app.session_state['export_dir']=str(demo)
    app.session_state['reference_export_dir']=str(out)
    app.run()
    app.radio(key='section').set_value('Reviewed reference evidence').run()
    assert not app.exception
    assert any('1 reviewed reference cases' in block.value for block in app.markdown)
    assert any(block.value=='I found it.' for block in app.text)
    app.radio(key='section').set_value('Ask the evidence').run()
    app.text_input(key='ask_question').set_value('found')
    app.button(key='ask_search').click().run()
    assert not app.exception
    assert any('Human-approved development reference label' in block.value for block in app.caption)
