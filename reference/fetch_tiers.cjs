// 查证两游蚀刻章品阶体系：方舟普通vs镀层成对素材+wiki文本；终末地品阶文本
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 2) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) {
      console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`);
      await sleep(800 * t);
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
  const base = __dirname;
  fs.mkdirSync(path.join(base, 'ak_pairs'), { recursive: true });

  // ===== A. PRTS 光荣之路 维基原文（品阶规则）=====
  console.log('===== A. PRTS wikitext =====');
  const wt = await getText('https://prts.wiki/index.php?title=' + encodeURIComponent('光荣之路') + '&action=raw');
  if (wt) {
    const lines = wt.split('\n').filter(l =>
      /镀层|套组|蚀刻章|晋升|勋章/.test(l)).slice(0, 40);
    fs.writeFileSync(path.join(base, 'prts_glorious_path.wikitext.txt'), lines.join('\n'));
    console.log(lines.slice(0, 25).join('\n'));
  }

  // ===== B. 普通 vs 镀层 成对素材 =====
  console.log('===== B. normal vs plated pairs =====');
  const all = JSON.parse(await getText('https://prts.wiki/api.php?action=query&list=allimages&aiprefix=' +
    encodeURIComponent('蚀刻章_“') + '&ailimit=500&format=json'));
  const map = {};
  for (const im of all.query.allimages) map[im.name] = im.url.startsWith('//') ? 'https:' + im.url : im.url;
  // 找出所有带 _镀层 的名字，配对下载
  const platedNames = Object.keys(map).filter(n => n.includes('_镀层'));
  console.log('plated count:', platedNames.length);
  let pi = 0;
  const pickSet = platedNames.slice(0, 6);   // 前6对
  for (const pn of pickSet) {
    pi++;
    const normalName = pn.replace('_镀层', '');
    if (map[pn]) await dl(map[pn], path.join(base, 'ak_pairs', `pair${pi}_plated.png`));
    await sleep(150);
    if (map[normalName]) await dl(map[normalName], path.join(base, 'ak_pairs', `pair${pi}_normal.png`));
    else console.log('no normal for', pn);
    await sleep(150);
  }

  // ===== C. Game8 页面文本（品阶描述）=====
  console.log('===== C. game8 text =====');
  const g8 = await getText('https://game8.jp/arknights-endfield/763938');
  if (g8) {
    const text = g8
      .replace(/<script[\s\S]*?<\/script>/g, '')
      .replace(/<style[\s\S]*?<\/style>/g, '')
      .replace(/<[^>]+>/g, '\n')
      .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
      .split('\n').map(s => s.trim()).filter(s => s.length > 2);
    const kw = text.filter((s, i) =>
      /勲章|銀|金|メッキ|加工|極秘|レア|ティア|ランク/.test(s)).slice(0, 60);
    fs.writeFileSync(path.join(base, 'game8_medal_text.txt'), kw.join('\n'));
    console.log(kw.join('\n').slice(0, 2200));
  }
})();
