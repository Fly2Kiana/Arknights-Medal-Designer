// 拉取真实摄影测试图（picsum = Unsplash 图库镜像，含人像/动物/物品/风景）
const fs = require('fs');
const path = require('path');
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function retry(fn, tag, n = 3) {
  for (let t = 1; t <= n; t++) {
    try { return await fn(); }
    catch (e) {
      console.log(`  retry${t} ${tag}: ${e.cause ? (e.cause.code || e.cause.message) : e.message}`);
      await sleep(900 * t);
    }
  }
  return null;
}
// 精选 ID：覆盖人像/宠物/物品/风景（picsum 的 id 对应固定真实照片）
(async () => {
  const dir = path.join(__dirname, '..', 'real_photos');
  fs.mkdirSync(dir, { recursive: true });
  const jobs = [
    ['portrait_woman', 64], ['portrait_man', 1005], ['portrait_girl', 129],
    ['pet_dog', 237], ['pet_pug', 1025], ['animal_bigcat', 1074],
    ['object_desk', 60], ['object_arch', 122], ['food_market', 292],
    ['landscape_river', 1015], ['landscape_canyon', 1016], ['landscape_mtn', 1018],
  ];
  for (const [name, id] of jobs) {
    if (!id) continue;
    const url = `https://picsum.photos/id/${id}/900/1100`;
    const ok = await retry(async () => {
      const r = await fetch(url, { headers: UA, redirect: 'follow' });
      if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { cause: { code: r.status } });
      const buf = Buffer.from(await r.arrayBuffer());
      if (buf.length < 5000) throw new Error('too small');
      fs.writeFileSync(path.join(dir, name + '.jpg'), buf);
      return true;
    }, name);
    if (ok) console.log('saved', name, fs.statSync(path.join(dir, name + '.jpg')).size);
    await sleep(400);
  }
})();
