// 修正版：协议相对URL处理 + 重点视频封面 + NGA 社区标准文本
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36', 'Referer': 'https://www.bilibili.com/' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 2) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) { console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`); await sleep(800 * t); }
  }
  return null;
}
const getJson = u => retry(() => fetch(u, { headers: UA }).then(r => r.json()), u.slice(-30));
function norm(u) {
  if (!u) return null;
  if (u.startsWith('//')) u = 'https:' + u;
  return u.replace(/^http:/, 'https:');
}
function dl(u, p, referer) {
  const h = Object.assign({}, UA);
  if (referer) h['Referer'] = referer;
  return retry(async () => {
    const r = await fetch(u, { headers: h });
    if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { cause: { code: r.status } });
    fs.writeFileSync(p, Buffer.from(await r.arrayBuffer()));
    console.log('saved', path.basename(p), fs.statSync(p).size);
    return true;
  }, path.basename(p), 2);
}
(async () => {
  const dir = path.join(__dirname, 'community');
  fs.mkdirSync(dir, { recursive: true });

  const targets = [
    ['BV14qNg6xEJZ', '还原终末地蚀刻章'],
    ['BV1EXGJ6QEY6', '实体镀彩蚀刻章教程'],
    ['BV1Fe41187Bc', '手工刻vs机器刻'],
    ['BV1sqhNzHEai', 'AT-6刷刻章镀层'],
  ];
  for (const [bv, tag] of targets) {
    const v = await getJson(`https://api.bilibili.com/x/web-interface/view?bvid=${bv}`);
    if (v && v.data) {
      console.log(`[${bv}] ${v.data.title}`);
      const pic = norm(v.data.pic);
      if (pic) await dl(pic, path.join(dir, `target_${tag.replace(/[/\\]/g, '_')}.jpg`));
    }
    await sleep(300);
  }

  // NGA 蚀刻章签名标准 AK/T 001-2020 文本（社区设计约定）
  console.log('== NGA standard thread ==');
  const nga = await retry(() => fetch('https://bbs.nga.cn/read.php?tid=22481713&rand=23', { headers: Object.assign({}, UA, { Referer: 'https://bbs.nga.cn/' }) }).then(r => r.text()), 'nga');
  if (nga) {
    const text = nga.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '')
      .replace(/<[^>]+>/g, '\n').split('\n').map(s => s.trim()).filter(s => s.length > 2);
    const pick = text.filter(s => /蚀刻章|签名|标准|AK\/T|线条|描边|圆|六边|金色|银|字体/.test(s)).slice(0, 60);
    fs.writeFileSync(path.join(dir, 'nga_standard.txt'), pick.join('\n'));
    console.log(pick.join('\n').slice(0, 1500));
  } else console.log('nga fail');
})();
