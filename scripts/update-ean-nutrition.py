"""Refresh a bounded set of explicitly contributed EANs from Open Food Facts.

No household data, names, prices or images are published. Unknown results are
negatively cached for one day; a rate limit or service error stops the batch.
"""
import argparse
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'custom_components/improved_shopping_list'))
from ean_common import validate_nutrition, NUTRITION_TTL
spec=importlib.util.spec_from_file_location('ean_common_builder',ROOT/'scripts/build-ean-common.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
FIELDS='code,nutriscore_grade,nutriscore_version,nova_group'
USER_AGENT='ImprovedShoppingListCommunity/1.0 (+https://github.com/TitoTB/Improved-Shopping-List)'


def classify(payload,code,now):
    product=payload.get('product') if isinstance(payload,dict) else None
    if not isinstance(product,dict):return {}
    if builder.gtin(str(product.get('code','')))!=code:raise ValueError('Response EAN mismatch')
    entry={'source':'openfoodfacts','license':'ODbL-1.0','checked_at':int(now)}
    grade=product.get('nutriscore_grade')
    if isinstance(grade,str) and grade.lower() in tuple('abcde'):
        entry['nutriscore']={'grade':grade.lower()}
        version=str(product.get('nutriscore_version',''))
        if len(version)==4 and version.isdigit() and version.startswith('20'):entry['nutriscore']['version']=version
    nova=product.get('nova_group')
    if type(nova) is int and 1<=nova<=4:entry['nova']=nova
    return validate_nutrition(entry) if 'nutriscore' in entry or 'nova' in entry else {}


def refresh(contributions,previous,limit=100,interval=4.2,fetch=None,wait=time.sleep,clock=time.time):
    if not 1<=limit<=100 or interval<4.2:raise ValueError('Limit must be 1..100 and interval at least 4.2 seconds')
    entries={code:validate_nutrition(row) for code,row in previous.get('nutrition',{}).items() if builder.gtin(code)==code}
    attempts={code:stamp for code,stamp in previous.get('attempts',{}).items() if builder.gtin(code)==code and type(stamp) in (int,float) and 0<stamp<=clock()}
    codes=sorted({*contributions.get('products',{}),*contributions.get('nutrition',{})})
    for code,row in contributions.get('nutrition',{}).items():
        row=validate_nutrition(row)
        if row['checked_at']>entries.get(code,{}).get('checked_at',0):entries[code]=row
    pending=[code for code in codes if builder.gtin(code)==code and clock()-max(entries.get(code,{}).get('checked_at',0),attempts.get(code,0))> (NUTRITION_TTL if code in entries and attempts.get(code,0)<=entries[code]['checked_at'] else 86400)]
    fetched=0;error=''
    for code in pending[:limit]:
        if fetched:wait(interval)
        try:
            payload=fetch(code) if fetch else request_product(code)
            entry=classify(payload,code,clock())
            attempts[code]=int(clock());fetched+=1
            if entry:entries[code]=entry
            print(json.dumps({'processed':fetched,'total':min(limit,len(pending)),'classified':len(entries)}),flush=True)
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            error=f'{type(exc).__name__}: {exc}'[:300]
            if isinstance(exc,HTTPError):exc.close()
            print(json.dumps({'stopped':True,'error':error}),flush=True);break
    return {'schema_version':1,'nutrition':dict(sorted(entries.items())),'attempts':dict(sorted(attempts.items()))}, {'requests':fetched,'classified':len(entries),'pending':max(0,len(pending)-fetched),'error':error}


def request_product(code):
    # OFF's canonical consumer barcode omits the optional GTIN-14 leading zero.
    query_code=code[1:] if len(code)==14 and code.startswith('0') else code
    url='https://world.openfoodfacts.org/api/v3/product/'+query_code+'?'+urlencode({'fields':FIELDS})
    try:response=urlopen(Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'}),timeout=20)
    except HTTPError as error:
        if error.code==404:return {}
        raise
    with response:

        raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Product response too large')
        return json.loads(raw)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--contributions',type=Path,default=ROOT/'data/ean-common-contributions.json');parser.add_argument('--previous',type=Path,default=ROOT/'data/ean-nutrition.json');parser.add_argument('--output',type=Path,default=ROOT/'data/ean-nutrition.json');parser.add_argument('--limit',type=int,default=100);args=parser.parse_args()
    contributions=json.loads(args.contributions.read_text(encoding='utf-8'));previous=json.loads(args.previous.read_text(encoding='utf-8')) if args.previous.exists() else {}
    data,summary=refresh(contributions,previous,args.limit)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
