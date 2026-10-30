import asyncio,json,time,ssl,sys
from pathlib import Path
import aiohttp
BASE='https://tienda.mercadona.es'
SEARCH='https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_mad1_es/query'
HEADERS={'X-Algolia-Application-Id':'7UZJKL1DJ0','X-Algolia-API-Key':'9d8f2e39e90df472b4f2e559a116fe17'}
async def main():
    print(json.dumps({'python':sys.version.split()[0],'openssl':ssl.OPENSSL_VERSION,'aiohttp':aiohttp.__version__}),flush=True)
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(),timeout=aiohttp.ClientTimeout(total=25)) as session:
        jobs=[('product','GET',BASE+'/api/products/69938/?lang=es&wh=mad1',None),('ean_search','POST',SEARCH,{'query':'8430543025611','hitsPerPage':5,'analytics':False,'clickAnalytics':False}),('name_search','POST',SEARCH,{'query':'Tomate rallado','hitsPerPage':5,'analytics':False,'clickAnalytics':False}),('category','GET',BASE+'/api/categories/855/?lang=es&wh=mad1',None)]
        for i,(stage,method,url,payload) in enumerate(jobs):
            if i:await asyncio.sleep(20)
            start=time.monotonic()
            try:
                async with session.request(method,url,json=payload,headers=HEADERS if method=='POST' else {'Accept':'application/json'}) as response:
                    result={'stage':stage,'status':response.status,'elapsed_ms':round((time.monotonic()-start)*1000)}
                    if response.status==200:
                        d=await response.json()
                        if stage=='product':
                            pi=d.get('price_instructions',{})
                            result.update(id=d.get('id'),ean=d.get('ean'),name=d.get('display_name'),brand=d.get('brand') or d.get('details',{}).get('brand'),price=pi.get('unit_price'),content=pi.get('unit_size'),unit=pi.get('size_format'),measure_price=pi.get('reference_price'),measure_unit=pi.get('reference_format'))
                        else:
                            rows=[]
                            def walk(o):
                                if isinstance(o,dict):
                                    if 'price_instructions' in o:rows.append(o)
                                    else:
                                        for v in o.values():walk(v)
                                elif isinstance(o,list):
                                    for v in o:walk(v)
                            walk(d)
                            result.update(products=len(rows),with_ean=sum(bool(r.get('ean')) for r in rows),samples=[{'id':r.get('id'),'name':r.get('display_name'),'ean':r.get('ean')} for r in rows[:3]])
                    print(json.dumps(result,ensure_ascii=False),flush=True)
                    if response.status in (403,429,503):
                        print(json.dumps({'stopped':True,'reason':'provider_rejection'}),flush=True);break
            except Exception as e:print(json.dumps({'stage':stage,'error':type(e).__name__}),flush=True);break
asyncio.run(main())
