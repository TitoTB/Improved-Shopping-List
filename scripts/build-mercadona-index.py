"""Build a compact public EAN index. Never execute code from the source snapshot."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"custom_components/improved_shopping_list"))
from ean_common import consensus, observed_at

SOURCE="https://huggingface.co/datasets/datania/mercadona-catalog"


def gtin(value):
    if not isinstance(value,str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})",value):return ""
    total=sum(int(digit)*(3 if i%2==0 else 1) for i,digit in enumerate(value[-2::-1]))
    return value.zfill(14) if (total+int(value[-1]))%10==0 else ""


def build(records,revision,updated_at,minimum=1000):
    if not re.fullmatch(r"[a-f0-9]{40}",revision):raise ValueError("Invalid source revision")
    candidates={};facts={};invalid=0
    observed_at(updated_at)
    for filename,record in records:
        if not isinstance(record,dict):raise ValueError("Invalid product JSON")
        identity=record.get("id")
        ean=gtin(record.get("ean"))
        if not ean or not isinstance(identity,str) or not re.fullmatch(r"[0-9]{1,12}",identity) or filename!=identity:
            invalid+=1;continue
        candidates.setdefault(ean,set()).add(identity)
        facts.setdefault(ean,[]).append(record)
        if len(candidates)>20000:raise ValueError("Too many products")
    products={ean:next(iter(ids)) for ean,ids in sorted(candidates.items()) if len(ids)==1}
    if len(products)<minimum:raise ValueError("Incomplete snapshot; keeping the previously published index")
    common={ean:consensus(facts[ean]) for ean in products}
    return {"schema_version":1,"source_url":SOURCE,"source_revision":revision,"source_updated_at":updated_at,
        "excluded":{"invalid":invalid,"ambiguous":sum(len(ids)>1 for ids in candidates.values())},"products":products,
        "common_schema_version":1,"common":common}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--revision",required=True)
    parser.add_argument("--updated-at",required=True)
    args=parser.parse_args()
    def records():
        for path in sorted((args.source/"products").glob("*.json")):
            if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError("Invalid product file")
            yield path.stem,json.loads(path.read_bytes())
    value=build(records(),args.revision,args.updated_at)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"entries":len(value["products"]),"source_revision":value["source_revision"],"excluded":value["excluded"]}))


if __name__=="__main__":main()
