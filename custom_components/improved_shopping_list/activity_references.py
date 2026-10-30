"""Meaningful purchase-option changes, without timestamps or internal bookkeeping."""
from .product_references import reference_key

FIELDS=("store","name","ean","reference_id","ticket_reference_id","url","brand","image_url",
        "content_quantity","content_unit","last_price","measure_price","nutriscore","active")


def values(reference):
    result={key:reference.get(key) for key in FIELDS}
    result["active"]=reference.get("active",True)
    for field,keys in (("last_price",("price","currency")),("measure_price",("price","quantity","unit","currency")),("nutriscore",("grade",))):
        value=result[field]
        result[field]={key:value.get(key) for key in keys} if isinstance(value,dict) else None
    return {key:None if value=="" else value for key,value in result.items()}


def reference_changes(before,after):
    def indexed(rows):
        return {row.get("id") or reference_key(row.get("store",""),row):row for row in rows if isinstance(row,dict)}
    old,new=indexed(before),indexed(after)
    changes=[]
    for uid in dict.fromkeys([*old,*new]):
        previous,current=old.get(uid),new.get(uid)
        left,right=values(previous or {}),values(current or {})
        # Enabled is implicit on a new option, not an added catalog field.
        if previous is None:left["active"]=right["active"]
        if current is None:right["active"]=left["active"]
        added=[key for key in FIELDS if left[key] is None and right[key] is not None]
        removed=[key for key in FIELDS if left[key] is not None and right[key] is None]
        updated=[key for key in FIELDS if left[key] is not None and right[key] is not None and left[key]!=right[key]]
        if not (added or removed or updated):continue
        row=current or previous
        changes.append({"id":uid,"store":row.get("store",""),"ean":row.get("ean",""),"name":row.get("name",""),
            "reference_id":row.get("reference_id",""),"action":"added" if previous is None else "removed" if current is None else "updated",
            "added_fields":added,"updated_fields":updated,"removed_fields":removed})
    return changes
