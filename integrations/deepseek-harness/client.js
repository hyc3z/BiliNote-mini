window.__ModuleLoader__.load({
 id:'@hyc3z/dsh-bilinote-mini',
 factory(require){
  const React=require('react'),h=React.createElement
  return {inject:['slots','locale'],apply(ctx){
   ctx.effect(()=>ctx.locale.register('bilinote',{zh:{open:'BiliNote 工作台',close:'收起工作台',external:'独立窗口',hint:'后端首次启动需要几秒；无法连接时请检查本地安装与日志。'},en:{open:'BiliNote workbench',close:'Collapse workbench',external:'Open window',hint:'Backend startup takes a few seconds. Check local installation and logs if unavailable.'}}))
   const t=ctx.locale.bind('bilinote')
   function Workbench(){const [open,setOpen]=React.useState(false);return h('section',{style:{width:'100%'}},h('div',{style:{display:'flex',gap:12,alignItems:'center'}},h('button',{type:'button',onClick:()=>setOpen(!open),'aria-expanded':open},t(open?'close':'open')),h('a',{href:'http://127.0.0.1:8483/',target:'_blank',rel:'noreferrer'},t('external'))),open&&h('div',null,h('p',null,t('hint')),h('iframe',{src:'http://127.0.0.1:8483/',title:'BiliNote',style:{width:'100%',height:'65vh',border:0,borderRadius:8},allow:'clipboard-write'})))}
   ctx.slots.inject('conversation.composer.dock',()=>ctx.slots.register({name:'conversation.composer.dock',id:'bilinote-workbench',order:20},Workbench))
  }}
 }
})
