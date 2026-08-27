// 抓取社区自制蚀刻章素材：B站视频封面 + 图文动态 + 相关搜索
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36', 'Referer': 'https://www.bilibili.com/' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 3) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) { console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`); await sleep(800 * t); }
  }
  return null;
}
const getJson = u => retry(() => fetch(u, { headers: UA }).then(r => r.json()), u.slice(-30));
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

  // 1. 已知视频封面
  const bvids = ['BV1Cg4y1T78n', 'BV1qv411n7rY', 'BV1p34y1q7gU'];
  for (const bv of bvids) {
    const v = await getJson(`https://api.bilibili.com/x/web-interface/view?bvid=${bv}`);
    if (v && v.data) {
      console.log(`[${bv}] ${v.data.title}`);
      await dl((v.data.pic || '').replace(/^http:/, 'https:'), path.join(dir, `cover_${bv}.jpg`));
    }
    await sleep(300);
  }

  // 2. 搜索：蚀刻章 客单/设计/自制
  for (const kw of ['蚀刻章 客单', '蚀刻章 设计', '自制 蚀刻章']) {
    const s = await getJson(`https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=${encodeURIComponent(kw)}&page=1`);
    if (s && s.data && s.data.result) {
      console.log(`== search: ${kw} ==`);
      for (const v of s.data.result.slice(0, 6)) {
        console.log('  ', v.bvid, v.title.replace(/<[^>]+>/g, ''));
        if (v.pic) await dl((v.pic || '').replace(/^http:/, 'https:'), path.join(dir, `s_${v.bvid}.jpg`));
        await sleep(200);
      }
    } else console.log(`search fail: ${kw}`);
    await sleep(600);
  }

  // 3. 图文动态（仿制新春前瞻素材展示）
  const op = await getJson('https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail?id=1160537959135445011');
  if (op && op.data && op.data.item) {
    const item = op.data.item;
    console.log('== opus ==', (item.title || item.content || '').slice(0, 60));
    const blocks = item.modules && item.modules.module_dynamic ? item.modules.module_dynamic.desc : null;
    const pics = (item.blocks && item.blocks.pictures) || (item.orig && item.orig.pictures) || [];
    const imgs = (item.modules && item.modules.module_dynamic && item.modules.module_dynamic.major) || null;
    let pi = 0;
    if (pics.length) {
      for (const p of pics) {
        pi++;
        await dl((p.img_src || p.img || '').replace(/^http:/, 'https:'), path.join(dir, `opus_${String(pi).padStart(2, '0')}.jpg`));
      }
    } else if (imgs && imgs.draw && imgs.draw.items) {
      for (const it of imgs.draw.items) {
        pi++;
        await dl((it.src || '').replace(/^http:/, 'https:'), path.join(dir, `opus_${String(pi).padStart(2, '0')}.jpg`));
      }
    }
    console.log('opus pics:', pi);
  } else console.log('opus fail');
})();
