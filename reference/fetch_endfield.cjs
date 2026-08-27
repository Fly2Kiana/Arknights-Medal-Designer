// v3：精准抓取——版本页蚀刻章图标 + B站API封面 + 9game攻略图
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 2) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) {
      console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`);
      await sleep(900 * t);
    }
  }
  return null;
}
const getText = u => retry(() => fetch(u, { headers: UA }).then(r => r.text()), u.slice(-40));
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
  const dir = path.join(__dirname, 'endfield2');
  fs.mkdirSync(dir, { recursive: true });
  const api = 'https://wiki.biligame.com/zmd/api.php?format=json&';

  // A. 版本页中文件名含「蚀刻章」的图标（慢速防限流）
  console.log('== A. version page medal icons ==');
  const versions = ['新潮起，故渊离', '零号委托', '影拓丰碑', '春晓时'];
  const seen = new Set();
  let idx = 0;
  for (const t of versions) {
    const q = await getText(api + 'action=query&prop=images&imlimit=120&titles=' +
      encodeURIComponent(t) + '&format=json');
    if (!q || q[0] === '<') { console.log('throttled, skip', t); await sleep(2500); continue; }
    let pages;
    try { pages = JSON.parse(q).query.pages; } catch (e) { console.log('json fail', t); await sleep(2500); continue; }
    for (const pid of Object.keys(pages)) {
      for (const im of (pages[pid].images || [])) {
        const fn = im.title.replace(/^文件:/, '');
        if (!/蚀刻章/i.test(fn) || seen.has(fn) || !/\.(png|jpg|jpeg|webp)$/i.test(fn)) continue;
        seen.add(fn);
        const info = await getText(api + 'action=query&prop=imageinfo&iiprop=url&titles=' +
          encodeURIComponent('文件:' + fn) + '&format=json');
        if (!info || info[0] === '<') { await sleep(2000); continue; }
        try {
          const ij = JSON.parse(info);
          for (const pid2 of Object.keys(ij.query.pages)) {
            const ii = ij.query.pages[pid2].imageinfo;
            if (ii && ii[0] && ii[0].url) {
              idx++;
              await dl(ii[0].url.startsWith('//') ? 'https:' + ii[0].url : ii[0].url,
                path.join(dir, 'medal_' + String(idx).padStart(2, '0') + '.png'));
            }
          }
        } catch (e) { console.log('info fail', fn); }
        await sleep(350);
      }
    }
  }
  console.log('medal icons total:', idx);

  // B. B站 API 视频封面
  console.log('== B. bilibili api cover ==');
  try {
    const bj = JSON.parse(await getText('https://api.bilibili.com/x/web-interface/view?bvid=BV1wcdtBQEzJ'));
    if (bj.data && bj.data.pic) {
      await dl(bj.data.pic.replace(/^http:/, 'https:'), path.join(dir, 'bili_cover.jpg'), 'https://www.bilibili.com/');
      console.log('video title:', bj.data.title);
    }
  } catch (e) { console.log('bili ERR', e.message); }

  // C. 9game 攻略文内嵌图
  console.log('== C. 9game article images ==');
  try {
    const html = await getText('https://www.9game.cn/mrfz/11679077.html');
    const urls = [...new Set((html.match(/https:\/\/img\.9game\.cn[^"'\s)]+\.(?:png|jpg|jpeg)/g) || []))].slice(0, 8);
    console.log('9game imgs:', urls.length);
    let ci = 0;
    for (const u of urls) { ci++; await dl(u, path.join(dir, 'ng_' + String(ci).padStart(2, '0') + '.jpg'), 'https://www.9game.cn/'); }
  } catch (e) { console.log('9game ERR', e.message); }
})();
