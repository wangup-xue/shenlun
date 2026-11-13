async function getJSON(path){const r=await fetch(path+'?t='+Date.now());if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}
function safe(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function safeUrl(s){return /^https?:\/\//i.test(String(s||''))?safe(s):'#'}
async function initJiangsu(){
 try{
  const d=await getJSON('data/jiangsu/cases.json');
  document.getElementById('cities').innerHTML=d.cities.map(x=>'<article class="jsc-card"><div class="jsc-city">'+safe(x.city)+' · '+safe(x.topic)+'</div><h3>'+safe(x.case)+'</h3><div class="jsc-tags">'+x.angles.map(t=>'<span class="jsc-tag">'+safe(t)+'</span>').join('')+'</div><a href="'+safeUrl(x.url)+'" target="_blank" rel="noopener">查阅当地政府官网 ↗</a></article>').join('');
 }catch(e){document.getElementById('cities').textContent='案例加载失败：'+e.message}
 try{
  const d=await getJSON('data/jiangsu/news.json');
  document.getElementById('updated').textContent='最近更新：'+(d.updated||'暂无')+'（北京时间）';
  const items=(d.items||[]).slice(0,80);
  document.getElementById('news').innerHTML=items.length?items.map(x=>'<article class="jsc-news"><a href="'+safeUrl(x.url)+'" target="_blank" rel="noopener">'+safe(x.title)+'</a><div class="jsc-meta">'+safe(x.source)+' · '+safe(x.date)+' · '+safe(x.category)+'</div>'+(x.summary?'<div class="jsc-summary">'+safe(x.summary)+'</div>':'')+'</article>').join(''):'暂无新闻线索，请稍后刷新。';
 }catch(e){document.getElementById('news').textContent='新闻数据暂不可用；每日更新任务首次运行后会生成。'}
 try{
  const d=await getJSON('data/jiangsu/leads.json'), all=d.items||[];
  const cities=['全部城市','江苏全省','全国/待核','南京','无锡','徐州','常州','苏州','南通','连云港','淮安','盐城','扬州','镇江','泰州','宿迁'];
  const section=document.getElementById('leads');
  section.innerHTML='<div class="jsc-filter"><label for="city-filter">按城市筛选：</label><select id="city-filter">'+cities.map(c=>'<option>'+safe(c)+'</option>').join('')+'</select><p class="jsc-note">分析依据为RSS标题与短摘要，不等同于全文研读。事实、数字及引语请以原文为准。</p></div><div id="lead-list" class="jsc-news-list"></div>';
  const render=()=>{const city=document.getElementById('city-filter').value;const rows=all.filter(x=>city==='全部城市'||x.city===city);document.getElementById('lead-list').innerHTML=rows.slice(0,80).map(x=>{const a=x.analysis||{};const p=a.policy_angles||[];const t=a.three_color_notes||{};return '<article class="jsc-news"><a href="'+safeUrl(x.url)+'" target="_blank" rel="noopener">'+safe(x.title)+'</a><div class="jsc-meta">'+safe(x.city)+' · '+safe(x.source)+' · '+safe(x.date)+' · '+safe(a.level)+'</div><div class="jsc-summary"><b>申论主题：</b>'+safe(a.topic)+'<br><b>总论点：</b>'+safe(a.thesis)+'</div><div class="jsc-summary"><b>分析角度：</b>'+p.map(safe).join('；')+'</div><div class="jsc-summary"><b>三色笔记·论点：</b>'+safe(t['论点'])+'<br><b>金句提炼：</b>'+safe(t['金句提炼'])+'<br><b>案例：</b>'+safe(t['案例'])+'</div><p class="jsc-note">'+safe(a.evidence_warning)+'</p></article>'}).join('')||'<p class="jsc-note">该筛选条件下暂无线索。</p>'};
  document.getElementById('city-filter').addEventListener('change',render);render();
 }catch(e){document.getElementById('leads').textContent='申论线索卡片暂不可用；每日更新任务运行后会生成。'}
}
document.addEventListener('DOMContentLoaded',initJiangsu);
