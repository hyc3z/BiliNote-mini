/** Move only explicitly labelled summaries; never mistake critical analysis for source views. */
export function splitQuickTake(markdown:string){
  const lines=markdown.split('\n')
  const index=lines.findIndex(line=>/^#{1,3}\s+(?:省流|AI\s*总结|全片总结|视频总结)\s*[:：]?\s*$/i.test(line.trim()))
  if(index<0)return {summary:'',body:markdown}
  const level=lines[index].match(/^#+/)![0].length
  let end=index+1
  while(end<lines.length){const heading=lines[end].match(/^(#{1,6})\s/);if(heading&&heading[1].length<=level)break;end++}
  const summary=lines.slice(index+1,end).join('\n').trim()
  if(!summary)return {summary:'',body:markdown}
  return {summary,body:[...lines.slice(0,index),...lines.slice(end)].join('\n').trim()}
}
