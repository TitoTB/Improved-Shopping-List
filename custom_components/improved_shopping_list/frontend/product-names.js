/** Comparison keys never replace the user's display spelling. */
export const productNameKey = value => String(value ?? "").normalize("NFKD")
  .replace(/\p{M}/gu, "").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

export function combinedTodoName(summary, description) {
  const text=value=>String(value??'').trim().replace(/\s+/g,' ');
  const name=text(summary), detail=text(description);
  if(!detail)return name;
  if(!name)return detail;
  const nameKey=productNameKey(name), detailKey=productNameKey(detail);
  if(nameKey===detailKey||nameKey.endsWith(' '+detailKey))return name;
  if(detailKey.startsWith(nameKey+' '))return detail;
  return name+' '+detail;
}

export function todoItemName(item, useDescription=false) {
  const summary=item.source_summary??item.summary??'';
  return useDescription?combinedTodoName(summary,item.source_description??item.description):String(summary);
}

export function namedTodoItem(item, useDescription=false) {
  if(!useDescription)return item;
  return {...item, source_summary:item.source_summary??item.summary??'',
    source_description:item.source_description??item.description??'',
    summary:todoItemName(item,true),description:''};
}
