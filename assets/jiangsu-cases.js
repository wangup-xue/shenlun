async function getJSON(path){const r=await fetch(path+'?t='+Date.now());if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}
function safe(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function initJiangsu(){
 try{
  const d=await getJSON('data/jiangsu/cases.json');
  document.getElementById('cities').innerHTML=d.cities.map(x=>'<article class="jsc-card"><div class="jsc-city">'+safe(x.city)+' · '+safe(x.topic)+'</div><h3>'+safe(x.case)+'</h3><div class="jsc-tags">'+x.angles.map(t=>'<span class="jsc-tag">'+safe(t)+'</span>').join('')+'</div><a href="'+safe(x.url)+'" target="_blank" rel="noopener">查阅当地政府官网 ↗</a></article>').join('');
 }catch(e){document.getElementById('cities').textContent='案例加载失败：'+e.message}
 try{
  const d=await getJSON('data/jiangsu/news.json');
  document.getElementById('updated').textContent='最近更新：'+(d.updated||'暂无')+'（北京时间）';
  const items=(d.items||[]).slice(0,80);
  document.getElementById('news').innerHTML=items.length?items.map(x=>'<article class="jsc-news"><a href="'+safe(x.url)+'" target="_blank" rel="noopener">'+safe(x.title)+'</a><div class="jsc-meta">'+safe(x.source)+' · '+safe(x.date)+' · '+safe(x.category)+'</div>'+(x.summary?'<div class="jsc-summary">'+safe(x.summary)+'</div>':'')+'</article>').join(''):'暂无新闻线索，请稍后刷新。';
 }catch(e){document.getElementById('news').textContent='新闻数据暂不可用；每日更新任务首次运行后会生成。'}
}
document.addEventListener('DOMContentLoaded',initJiangsu);
