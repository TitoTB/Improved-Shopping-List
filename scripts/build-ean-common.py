"""Build store-independent EAN facts, publishing no private catalog fields."""
import argparse
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha1
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'custom_components/improved_shopping_list'))
from ean_common import brand, brand_key, content_key, validate


def gtin(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9]{8}|[0-9]{12,14})',value):return ''
    total=sum(int(d)*(3 if i%2==0 else 1) for i,d in enumerate(value[-2::-1]))
    return value.zfill(14) if (total+int(value[-1]))%10==0 and not(len(value)==13 and value.startswith('2')) else ''


def import_catalog(data,previous=None):
    products=deepcopy((previous or {}).get('products',{}))
    if data.get('kind')!='improved-shopping-list-catalog-export' or not isinstance(data.get('products'),list):
        raise ValueError('Expected a catalog export')
    for product in data['products']:
        for ref in product.get('commercial_references',[]):
            code=gtin(ref.get('ean'))
            if not code or ref.get('active') is False:continue
            fields={}
            if ref.get('brand'):fields['brand']=brand(ref['brand'])
            if ref.get('sale_mode')!='weight' and ref.get('content_confirmed') and content_key(ref.get('content_quantity'),ref.get('content_unit')):
                fields.update(content_quantity=ref['content_quantity'],content_unit=ref['content_unit'])
                if type(ref.get('pack_count')) is int:fields['pack_count']=ref['pack_count']
            fields=validate(fields)
            if not fields:continue
            store=ref.get('store') or 'catalog'
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',store):continue
            observation={'store':store,**fields}
            rows=products.setdefault(code,[])
            if observation not in rows:rows.append(observation)
    return {'schema_version':1,'products':dict(sorted(products.items()))}


def combine(observations):
    fields={};conflicts=set();origins=set()
    for row in observations:
        origins.add(row['store']);conflicts.update(row.get('conflicts',[]))
    for field,key in (('brand',brand_key),('pack_count',lambda value:value)):
        choices={key(row[field]):row[field] for row in observations if row.get(field)}
        if len(choices)==1 and field not in conflicts:fields[field]=next(iter(choices.values()))
        elif len(choices)>1:conflicts.add(field)
    contents={content_key(row.get('content_quantity'),row.get('content_unit')):(row.get('content_quantity'),row.get('content_unit')) for row in observations if row.get('content_quantity')}
    contents.pop(None,None)
    if len(contents)==1 and 'content' not in conflicts:fields['content_quantity'],fields['content_unit']=next(iter(contents.values()))
    elif len(contents)>1:conflicts.add('content')
    if conflicts:fields['conflicts']=sorted(conflicts)
    return {**validate(fields),'origins':sorted(origins)}


def build(contributions,mercadona):
    rows=deepcopy(contributions.get('products',{}))
    for code,fields in mercadona.get('common',{}).items():
        if gtin(code)==code:rows.setdefault(code,[]).append({'store':'mercadona',**validate(fields)})
    products={}
    for code,observations in sorted(rows.items()):
        if gtin(code)!=code or not isinstance(observations,list):raise ValueError('Invalid EAN contribution')
        sanitized=[{'store':row['store'],**validate({k:v for k,v in row.items() if k!='store'})} for row in observations]
        row=combine(sanitized)
        if any(row.get(field) for field in ('brand','content_quantity','pack_count')):products[code]=row
    revision=sha1(json.dumps(products,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'schema_version':1,'revision':revision,'updated_at':datetime.now(UTC).isoformat(),'products':products}


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--contributions',type=Path,default=ROOT/'data/ean-common-contributions.json');parser.add_argument('--mercadona',type=Path,default=ROOT/'data/mercadona-index.json');parser.add_argument('--output',type=Path,default=ROOT/'data/ean-common.json');parser.add_argument('--import-catalog',type=Path,action='append',default=[]);args=parser.parse_args()
    contributions=json.loads(args.contributions.read_text(encoding='utf-8')) if args.contributions.exists() else {'schema_version':1,'products':{}}
    for path in args.import_catalog:contributions=import_catalog(json.loads(path.read_text(encoding='utf-8-sig')),contributions)
    if args.import_catalog:write(args.contributions,contributions)
    result=build(contributions,json.loads(args.mercadona.read_text(encoding='utf-8')));write(args.output,result)
    print(json.dumps({'entries':len(result['products']),'contributed_eans':len(contributions['products']),'fields':{field:sum(field in row for row in result['products'].values()) for field in ('brand','content_quantity','content_unit','pack_count')}}))


if __name__=='__main__':main()
