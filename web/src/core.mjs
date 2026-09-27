export const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
export const minutes = t => Number(t.slice(0, 2)) * 60 + Number(t.slice(3));
export function parseWeeks(value, total = 60) {
  const result = new Set();
  const text = String(value).replace(/[，、]/g, ',').replace(/\s/g, '').replace(/周/g, '');
  if (!text) throw new Error('请填写上课周次，例如 1-16 或 1-16单');
  for (const token of text.split(',')) {
    const m = token.match(/^(\d+)(?:-(\d+))?([单双])?$/);
    if (!m) throw new Error('周次格式应为 1-16、1-16单、2-16双 或 1-8,10,12-16');
    const a = Number(m[1]), b = Number(m[2] || m[1]);
    if (a < 1 || b < a || b > total) throw new Error(`周次须在 1–${total} 之间，且起始周不大于结束周`);
    for (let w = a; w <= b; w++) if (!m[3] || (m[3] === '单' ? w % 2 === 1 : w % 2 === 0)) result.add(w);
  }
  if (!result.size) throw new Error('所选周次没有上课周');
  return [...result].sort((a,b) => a-b);
}
export function addDays(iso, n) { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0,10); }
export function dateInZone(zone, now = new Date()) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone:zone, year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).map(x=>[x.type,x.value]));
  return {date:`${p.year}-${p.month}-${p.day}`, time:`${p.hour}:${p.minute}`};
}
export function weekOf(start, date) { return Math.floor((Date.parse(date+'T00:00:00Z')-Date.parse(start+'T00:00:00Z')) / 604800000)+1; }
export function occurrences(data, week) {
  return data.courses.flatMap(c=> c.sessions.filter(s=>parseWeeks(s.weeks,data.settings.totalWeeks).includes(week)).map(s=>({...s, location:s.location||c.location, course:c, date:addDays(data.settings.startDate,(week-1)*7+s.day-1)}))).sort((a,b)=>a.day-b.day || minutes(a.start)-minutes(b.start));
}
export function conflicts(courses, total) {
  const all=courses.flatMap(c=>c.sessions.map(s=>({...s,name:c.name,active:parseWeeks(s.weeks,total)}))), found=[];
  for (let i=0;i<all.length;i++) for(let j=i+1;j<all.length;j++) {
    const a=all[i],b=all[j];
    if(a.day===b.day && minutes(a.start)<minutes(b.end) && minutes(b.start)<minutes(a.end) && a.active.some(w=>b.active.includes(w))) found.push(`${a.name} / ${b.name}（${weekdays[a.day-1]} ${a.start}–${a.end}）`);
  }
  return [...new Set(found)];
}
// Assign overlapping sessions separate lanes, keeping every course clickable.
export function lanes(items) {
  const sorted=[...items].sort((a,b)=>minutes(a.start)-minutes(b.start)), groups=[];
  for(const item of sorted) {
    let g=groups.at(-1);
    if(!g || minutes(item.start)>=g.end) {g={end:0,items:[],ends:[]};groups.push(g);}
    let lane=g.ends.findIndex(end=>end<=minutes(item.start));if(lane<0) lane=g.ends.length;
    g.ends[lane]=minutes(item.end);g.end=Math.max(g.end,minutes(item.end));g.items.push({...item,lane});
  }
  return groups.flatMap(g=>g.items.map(x=>({...x,laneCount:g.ends.length})));
}
