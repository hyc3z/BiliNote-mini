/** Browser-native PDF export with selectable text and embedded loaded frames. */
export async function exportPdf(article:HTMLElement,title:string,source:string){
  const popup=window.open('','_blank')
  if(!popup)throw new Error('请允许此页面打开导出窗口后重试。')
  const doc=popup.document
  doc.title=title+' · BiliNote'
  const style=doc.createElement('style')
  style.textContent=`@page{size:A4;margin:18mm 16mm}body{font:11pt/1.8 "Microsoft YaHei","Segoe UI",sans-serif;color:#222;background:white;max-width:180mm;margin:20px auto}h1{font-size:21pt}h2{font-size:16pt;margin-top:24px}h3{font-size:13pt}h1,h2,h3,h4{break-after:avoid}p,li{orphans:3;widows:3}a{color:#644097;text-decoration:none;overflow-wrap:anywhere}img{max-width:100%;max-height:180mm;object-fit:contain}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px}.mini-frame{display:block;margin:16px 0;break-inside:avoid}.mini-frame small{display:block;color:#666;font-size:9pt}.paired-original{display:block;border-left:3px solid #aaa;background:#f5f5f5;padding:12px;margin:18px 0}.paired-original-label{display:block;font-size:9pt;color:#666;margin-bottom:8px}.paired-original-line{display:block;margin:6px 0}.paired-original-line small{font-style:normal;color:#777;margin-right:12px;font-size:8pt}.paired-original em{font-style:italic}button,.export-status{padding:12px;background:#eee;border:0;margin:12px 0}.export-status{color:#444}header{border-bottom:1px solid #ddd;margin-bottom:20px;padding-bottom:12px}header p{font-size:9pt;color:#666}@media print{button,.export-status{display:none}body{margin:0;max-width:none}}`
  doc.head.append(style)
  const heading=doc.createElement('header'),name=doc.createElement('h1'),link=doc.createElement('a')
  name.textContent=title;link.textContent='原视频：'+source;link.href=source
  heading.append(name,link);doc.body.append(heading)
  const status=doc.createElement('p');status.className='export-status';status.textContent='正在准备截图，请稍候…';doc.body.append(status)
  const copy=article.cloneNode(true) as HTMLElement
  copy.removeAttribute('style');copy.querySelectorAll('[id]').forEach(n=>n.removeAttribute('id'))
  copy.querySelectorAll('button').forEach(n=>{const warning=doc.createElement('small');warning.textContent='此处截图未能加载，可回笔记页重试后导出。';n.replaceWith(warning)})
  const images=Array.from(copy.querySelectorAll('img'))
  images.forEach(img=>{img.src=new URL(img.getAttribute('src')||'',window.location.href).href;img.loading='eager'})
  doc.body.append(copy)
  let failed=0
  await Promise.all(images.map(img=>new Promise<void>(resolve=>{
    let settled=false
    const done=(ok:boolean)=>{if(settled)return;settled=true;clearTimeout(timer);if(!ok){failed++;const text=doc.createElement('small');text.textContent=(img.alt||'截图')+'：未能加载';img.replaceWith(text)}resolve()}
    const timer=setTimeout(()=>done(false),90000)
    img.onload=()=>done(true);img.onerror=()=>done(false)
    if(img.complete)done(img.naturalWidth>0)
  })))
  if(popup.closed)return
  await doc.fonts.ready
  status.textContent=failed?`${failed} 张截图未能加载。可返回笔记页重试，或继续保存当前版本。`:'已准备完成。打印窗口中选择“另存为 PDF”。'
  const print=doc.createElement('button');print.textContent='打印 / 另存为 PDF';print.onclick=()=>popup.print();doc.body.insertBefore(print,copy)
  if(!failed){popup.focus();popup.print()}
}
