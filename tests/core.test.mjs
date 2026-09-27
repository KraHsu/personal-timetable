import test from 'node:test';
import assert from 'node:assert/strict';
import {parseWeeks,weekOf,dateInZone,addDays,occurrences,conflicts,lanes} from '../public/core.mjs';
test('week expressions include odd/even, gaps and Chinese punctuation',()=>{
 assert.deepEqual(parseWeeks('1-8单，10，12-16双',20),[1,3,5,7,10,12,14,16]);
 for(const value of ['0','5-2','1-21','1,,2','2单','1-3x'])assert.throws(()=>parseWeeks(value,20));
});
test('week boundaries do not depend on local DST or current device timezone',()=>{
 assert.equal(weekOf('2026-03-02','2026-03-08'),1);assert.equal(weekOf('2026-03-02','2026-03-09'),2);
 assert.equal(weekOf('2026-09-07','2026-09-06'),0);assert.equal(addDays('2026-12-28',6),'2027-01-03');
 assert.deepEqual(dateInZone('Asia/Shanghai',new Date('2026-09-27T16:05:00Z')),{date:'2026-09-28',time:'00:05'});
});
const s=(weeks,start='08:00',end='10:00')=>({weeks,start,end,day:1});
const c=(name,sessions)=>({name,sessions});
test('alternating weeks are not conflicts; partial overlap is',()=>{
 assert.equal(conflicts([c('A',[s('1-16单')]),c('B',[s('2-16双')])],20).length,0);
 assert.equal(conflicts([c('A',[s('1-16')]),c('B',[s('2-16双','09:00','11:00')])],20).length,1);
 assert.equal(conflicts([c('A',[s('1-16')]),c('B',[s('1-16','10:00','12:00')])],20).length,0);
});
test('week selection and overlapping lanes retain all occurrences',()=>{
 const data={settings:{startDate:'2026-09-07',totalWeeks:20},courses:[c('A',[s('1-16单')]),c('B',[s('2-16双')])]};
 assert.equal(occurrences(data,2)[0].course.name,'B');assert.equal(occurrences(data,2)[0].date,'2026-09-14');
 const result=lanes([s('1','08:00','11:00'),s('1','09:00','10:00'),s('1','10:00','12:00'),s('1','12:00','13:00')]);
 assert.deepEqual(result.map(x=>[x.lane,x.laneCount]),[[0,2],[1,2],[1,2],[0,1]]);
});
test('each week uses its session location and unscheduled courses create no events',()=>{
 const data={settings:{startDate:'2026-09-21',totalWeeks:20},courses:[{name:'A',location:'教室',sessions:[s('1-2'),{...s('3'),location:'线上'}]},{name:'待定课程',sessions:[]}]};
 assert.equal(occurrences(data,1)[0].location,'教室');
 assert.equal(occurrences(data,3)[0].location,'线上');
 assert.equal(occurrences(data,4).length,0);
 assert.equal(conflicts(data.courses,20).length,0);
});
