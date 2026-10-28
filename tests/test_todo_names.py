"""Native product identity is consistent for mappings, entities and settings."""
from types import SimpleNamespace

import pytest

from custom_components.improved_shopping_list.todo_names import combined_name, item_name, named_item


@pytest.mark.parametrize(('summary','description','expected'),[
    (' Leche ',' de  avena ','Leche de avena'), ('Leche de avena','DE AVENA','Leche de avena'),
    ('Leche','Leche de avena','Leche de avena'), ('Seitán','SEITAN','Seitán'),
    ('Chocolate','late','Chocolate late'), ('Leche','','Leche'), ('','de avena','de avena'),
])
def test_combined_names(summary, description, expected):
    assert combined_name(summary,description) == expected


def test_policy_preserves_notes_other_lists_and_source_uid():
    snapshot={'description_as_name':{'todo.bring':True}}
    raw={'uid':'oat','summary':'Leche','description':'de avena','status':'needs_action'}
    assert item_name(snapshot,'todo.bring',raw) == 'Leche de avena'
    assert item_name(snapshot,'todo.local',raw) == 'Leche'
    assert item_name(SimpleNamespace(snapshot=snapshot),'todo.bring',SimpleNamespace(**raw)) == 'Leche de avena'
    named=named_item(snapshot,'todo.bring',raw)
    assert named['uid'] == raw['uid'] and named['description'] == ''
    assert named_item(snapshot,'todo.bring',named) == named
    assert raw == {'uid':'oat','summary':'Leche','description':'de avena','status':'needs_action'}
