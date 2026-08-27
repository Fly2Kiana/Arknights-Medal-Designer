// 下载明日方舟/终末地蚀刻章参考素材（经本地代理）
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36', 'Referer': 'https://prts.wiki/' };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag) {
  for (let t = 1; t <= 4; t++) {
    try { return await fn(); }
    catch (e) {
      const why = e.cause ? (e.cause.code || e.cause.message) : e.message;
      console.log(`  retry${t} ${tag}: ${why}`);
      await sleep(1200 * t);
    }
  }
  throw new Error('exhausted: ' + tag);
}
const get = (u) => retry(() => fetch(u, { headers: UA }).then(r => r.text()), u.slice(-40));
const dl = async (u, p) => {
  await retry(async () => {
    const r = await fetch(u, { headers: UA });
    if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { cause: { code: r.status } });
    fs.writeFileSync(p, Buffer.from(await r.arrayBuffer()));
  }, path.basename(p));
  console.log('saved', path.basename(p));
};
(async () => {
  const dir = __dirname;
  // 1. PRTS 干员晋升奖章系列
  console.log('step1: query promo list...');
  const promo = JSON.parse(await get('https://prts.wiki/api.php?action=query&list=allimages&aiprefix=' +
    encodeURIComponent('蚀刻章_干员晋升奖章') + '&ailimit=20&format=json'));
  console.log('step1 ok, files:', promo.query.allimages.length);
  let i = 0;
  for (const im of promo.query.allimages) {
    i++;
    await dl(im.url.startsWith('//') ? 'https:' + im.url : im.url,
      path.join(dir, 'prts', 'promo_' + String(i).padStart(2, '0') + '.png'));
  }
  // 2. 活动章 + 镀层对比样张
  const all = JSON.parse(await get('https://prts.wiki/api.php?action=query&list=allimages&aiprefix=' +
    encodeURIComponent('蚀刻章_“') + '&ailimit=500&format=json'));
  const map = {};
  for (const im of all.query.allimages) map[im.name] = im.url.startsWith('//') ? 'https:' + im.url : im.url;
  const picks = ['蚀刻章_“不朽”.png', '蚀刻章_“不畏苦暗”.png', '蚀刻章_“与灾异同行”.png',
    '蚀刻章_“与灾异同行”_镀层.png', '蚀刻章_“一星萤火”.png'];
  let j = 0;
  for (const p of picks) {
    j++;
    if (map[p]) await dl(map[p], path.join(dir, 'prts', 'event_' + String(j).padStart(2, '0') + '.png'));
    else console.log('miss', p);
  }
  // 3. 终末地 BWIKI：蚀刻章 / 影拓丰碑
  try {
    let k = 0;
    const zf = JSON.parse(await get('https://wiki.biligame.com/zmd/api.php?action=query&list=allimages&aiprefix=' +
      encodeURIComponent('蚀刻章') + '&ailimit=30&format=json'));
    console.log('endfield 蚀刻章 files:', zf.query.allimages.length);
    for (const im of zf.query.allimages) {
      k++;
      await dl(im.url.startsWith('//') ? 'https:' + im.url : im.url,
        path.join(dir, 'endfield', 'zmd_' + String(k).padStart(2, '0') + '.png'));
    }
    const yt = JSON.parse(await get('https://wiki.biligame.com/zmd/api.php?action=query&list=allimages&aiprefix=' +
      encodeURIComponent('影拓丰碑') + '&ailimit=30&format=json'));
    console.log('endfield 影拓丰碑 files:', yt.query.allimages.length);
    for (const im of yt.query.allimages) {
      k++;
      await dl(im.url.startsWith('//') ? 'https:' + im.url : im.url,
        path.join(dir, 'endfield', 'yt_' + String(k).padStart(2, '0') + '.png'));
    }
  } catch (e) { console.log('zmd ERR', e.message); }
})().catch(e => {
  console.error('ERR', e.message, '| cause:', e.cause && (e.cause.code || e.cause.message));
  process.exit(1);
});
